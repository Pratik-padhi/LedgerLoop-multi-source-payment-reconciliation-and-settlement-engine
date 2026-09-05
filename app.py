"""
LedgerLoop v2.1 — Controller UI Server
========================================

Runs the full reconciliation pipeline ONCE at startup, holds results in memory,
and exposes them via four read-only JSON endpoints plus a single-page UI.

ARCHITECTURAL BOUNDARY
-----------------------
This module:
  - imports result types and pipeline entry points
  - runs the pipeline exactly as the existing tests do
  - serialises already-computed results to JSON
  - exposes the existing SettlementQAAgent via a /api/qa endpoint

This module DOES NOT:
  - implement matching logic
  - duplicate any Tier 1/2/3 decision
  - call Gemini for reconciliation
  - modify any result object
  - consult the ground-truth evaluation file

Endpoints
---------
  GET  /                       → serves ui/index.html
  GET  /api/overview           → summary counts + per-tier stats
  GET  /api/exceptions         → all HUMAN_REVIEW + UNRESOLVED results (full detail)
  GET  /api/transaction/<id>   → single transaction detail (any tier)
  POST /api/qa                 → {"question": "..."} → QAAnswer as JSON
"""

import json
import os
import sys

# Make sure the project root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, send_from_directory, abort

from core.match_exact import run_tier1, get_residue
from core.match_fuzzy import run_tier2
from core.match_llm import (
    run_tier3,
    retry_tier3_transaction,
    GeminiLLMClient,
    GeminiFallbackClient,
    LLMAdjudicator,
    STATUS_MATCH,
    STATUS_HUMAN_REVIEW,
    STATUS_UNRESOLVED,
    STATUS_AI_RETRY_REQUIRED,
)
from core.match_split import (
    run_stage3,
    retry_stage3_transaction,
    SplitStatus,
    SplitResult,
)
from core.qa_agent import build_qa_agent

# ---------------------------------------------------------------------------
# Pipeline — run once at module load so the server starts hot
# ---------------------------------------------------------------------------

_DATA_DIR = os.environ.get(
    "LEDGERLOOP_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)


def _consumed_bank_ids(r1, r2, r3) -> set:
    """Bank source_row_ids already claimed by one-to-one matching (Tier 1/2/3)."""
    consumed: set[str] = set()
    for results in (r1, r2, r3):
        for r in results:
            bank_id = getattr(r, "matched_records", {}).get("bank")
            if bank_id:
                consumed.add(bank_id)
    return consumed


def _stage3_pending_txns(r3) -> list[dict]:
    """Build Stage 3 pending transactions from the Tier 3 residue.

    Stage 3 is the split / multi-payment / partial pass. It runs only on
    transactions Tier 3 could not resolve one-to-one (AI_RETRY_REQUIRED,
    HUMAN_REVIEW, UNRESOLVED) — never on anything Tier 3 already matched.
    """
    pending = []
    for r in r3:
        if r.status != STATUS_MATCH:
            pending.append({
                "transaction_id": r.transaction_id,
                "gateway_row_id": r.matched_records.get("gateway"),
                "ledger_row_id": r.matched_records.get("ledger"),
            })
    return pending


def _run_pipeline():
    """Execute the full reconciliation pipeline and return all results.

    Returns an extra pair (r4, summary4) for the Stage 3 split/multi-payment
    pass over the Tier 3 residue.
    """
    r1, summary1, matcher = run_tier1(data_dir=_DATA_DIR, return_matcher=True)
    residue1 = get_residue(r1)
    r2, summary2 = run_tier2(residue1, matcher)
    r3, summary3 = run_tier3(r2, matcher)   # uses env LLM_PROVIDER / GEMINI_API_KEY if set

    # Stage 3: split / multi-payment reconciliation over Tier 3 residue.
    already_consumed = _consumed_bank_ids(r1, r2, r3)
    pending_txns = _stage3_pending_txns(r3)
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    stage3_llm = (
        GeminiFallbackClient()
        if provider == "gemini" or os.environ.get("GEMINI_API_KEY")
        else None
    )
    r4, summary4 = run_stage3(
        matcher.gateway_records,
        matcher.bank_records,
        matcher.ledger_records,
        already_consumed,
        pending_txns,
        llm_client=stage3_llm,
    )
    return r1, summary1, r2, summary2, r3, summary3, r4, summary4, matcher


print("LedgerLoop: running reconciliation pipeline…", flush=True)
_r1, _summary1, _r2, _summary2, _r3, _summary3, _r4, _summary4, _matcher = _run_pipeline()
print(
    f"  Tier 1: {_summary1.matched_count} matched / "
    f"{_summary1.partial_match_count} partial / "
    f"{_summary1.unresolved_count} unresolved",
    flush=True,
)
print(
    f"  Tier 2: {_summary2.matched_count} matched from residue",
    flush=True,
)
print(
    f"  Tier 3: {_summary3.match_count} matched / "
    f"{_summary3.human_review_count} human review / "
    f"{_summary3.unresolved_count} unresolved",
    flush=True,
)
print(
    f"  Stage 3: {_summary4.match_count} matched / "
    f"{_summary4.partial_count} partial / "
    f"{_summary4.ambiguous_count} ambiguous / "
    f"{_summary4.ai_retry_count} ai-retry / "
    f"{_summary4.unresolved_count} unresolved "
    f"over {_summary4.total_evaluated} pending",
    flush=True,
)

# ---------------------------------------------------------------------------
# Bank rows claimed by Stage 3 MATCH results — needed to keep per-transaction
# retry from re-using rows another split already consumed.
# ---------------------------------------------------------------------------

_stage3_consumed: set[str] = set()
for r in _r4:
    if r.status == SplitStatus.MATCH:
        for bank_id in r.bank_row_ids:
            _stage3_consumed.add(bank_id)

# ---------------------------------------------------------------------------
# Build the authoritative result index for per-transaction lookups.
# Priority: Stage 3 > Tier 3 > Tier 2 (matched) > Tier 1.
# ---------------------------------------------------------------------------

_index: dict[str, dict] = {}

for r in _r1:
    _index[r.transaction_id] = {"tier": "TIER_1", "data": r.to_dict()}

for r in _r2:
    if r.status == "MATCHED":
        _index[r.transaction_id] = {"tier": "TIER_2", "data": r.to_dict()}

for r in _r3:
    _index[r.transaction_id] = {"tier": "TIER_3", "data": r.to_dict()}

for r in _r4:
    _index[r.transaction_id] = {"tier": "STAGE_3", "data": r.to_dict()}

# ---------------------------------------------------------------------------
# Overview KPIs — computed once at startup, read-only from here on.
# ---------------------------------------------------------------------------

_gw_amount_by_source: dict[str, float] = {}
for r in _matcher.gateway_records:
    _gw_amount_by_source[r.source_row_id] = float(r.amount.normalized)

_gateway_value = sum(_gw_amount_by_source.values(), 0.0)
_total_transactions = len(_index)
_matched_count = sum(
    1 for e in _index.values()
    if e["data"].get("status") in ("MATCH", "MATCHED")
)
_exception_count = _total_transactions - _matched_count
_reconciliation_rate = (
    round(_matched_count / _total_transactions * 100, 1)
    if _total_transactions > 0 else 0.0
)

_reconciled_value = 0.0
for entry in _index.values():
    d = entry["data"]
    if d.get("status") in ("MATCH", "MATCHED"):
        gw_id = (d.get("matched_records") or {}).get("gateway")
        if gw_id and gw_id in _gw_amount_by_source:
            _reconciled_value += _gw_amount_by_source[gw_id]

_settlement_variance = 0.0
for r in _r4:
    if r.status == SplitStatus.MATCH and r.settlement and r.settlement.get("variance") is not None:
        _settlement_variance += float(r.settlement["variance"])

# ---------------------------------------------------------------------------
# Settlement Q&A agent (read-only wrapper over pipeline results)
# ---------------------------------------------------------------------------

_qa_agent = build_qa_agent(
    _r1, _r2, _r3, _r4,
    use_llm_for_explanations=True,
)

print("  Q&A agent ready.", flush=True)
print("LedgerLoop: pipeline ready — serving UI.", flush=True)

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(_UI_DIR, "index.html")


@app.route("/<path:filename>")
def ui_asset(filename):
    """Serve static assets (CSS, JS, etc.) from the ui/ directory."""
    return send_from_directory(_UI_DIR, filename)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# /api/overview  — summary counts derived entirely from pipeline results
# ---------------------------------------------------------------------------

@app.route("/api/overview")
def api_overview():
    # Tier 1 stats (before residue handoff)
    t1 = _summary1.to_dict()

    # Tier 2 stats (from residue)
    t2 = _summary2.to_dict()

    # Tier 3 final stats (from Tier-2 residue)
    t3 = _summary3.to_dict()

    # Stage 3 split / multi-payment stats (from Tier-3 residue)
    t4 = _summary4.to_dict()

    # Aggregate final status counts across all tiers
    # (every transaction appears in _index under its authoritative tier)
    status_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    rule_counts: dict[str, int] = {}

    for entry in _index.values():
        d = entry["data"]
        s = d.get("status", "UNKNOWN")
        t = entry["tier"]
        rule = d.get("rule") or "NONE"
        status_counts[s] = status_counts.get(s, 0) + 1
        tier_counts[t] = tier_counts.get(t, 0) + 1
        rule_counts[rule] = rule_counts.get(rule, 0) + 1

    total = len(_index)

    # LLM model chain (built-in defaults + env overrides)
    _primary = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    _env_chain = [
        m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()
    ]
    llm_models = list(dict.fromkeys([_primary, *_env_chain]))

    return jsonify({
        "total_transactions": total,
        "status_counts": status_counts,
        "tier_counts": tier_counts,
        "rule_counts": rule_counts,
        "tier1_summary": t1,
        "tier2_summary": t2,
        "tier3_summary": t3,
        "stage3_summary": t4,
        "llm_calls_made": t3["llm_calls_made"],
        "llm_recommendations_validated": t3["llm_recommendations_validated"],
        "llm_recommendations_rejected": t3["llm_recommendations_rejected"],
        "gateway_value": float(_gateway_value),
        "reconciled_value": float(_reconciled_value),
        "reconciliation_rate": _reconciliation_rate,
        "exception_count": _exception_count,
        "settlement_variance": float(_settlement_variance),
        "dataset": os.path.basename(os.path.abspath(_DATA_DIR)),
        "gateway_rows": len(_matcher.gateway_records),
        "bank_rows": len(_matcher.bank_records),
        "ledger_rows": len(_matcher.ledger_records),
        "llm_models": llm_models,
    })


# ---------------------------------------------------------------------------
# /api/exceptions — all transactions needing attention
# ---------------------------------------------------------------------------

@app.route("/api/exceptions")
def api_exceptions():
    exceptions = []
    for tid, entry in sorted(_index.items()):
        d = entry["data"]
        status = d.get("status", "UNKNOWN")
        if status in (
            STATUS_HUMAN_REVIEW, STATUS_UNRESOLVED, STATUS_AI_RETRY_REQUIRED,
            SplitStatus.AMBIGUOUS, SplitStatus.AI_RETRY_REQUIRED,
            SplitStatus.PARTIAL, SplitStatus.UNRESOLVED,
        ):
            exceptions.append({
                "transaction_id": tid,
                "tier": entry["tier"],
                "status": status,
                "rule": d.get("rule"),
                "reason": d.get("reason"),
                "matched_records": d.get("matched_records", {}),
                "bank_row_ids": d.get("bank_row_ids", []),
                "received": d.get("received"),
                "outstanding": d.get("outstanding"),
                "evidence": d.get("evidence", {}),
                "llm_consulted": d.get("llm_consulted", False),
            })
    return jsonify({"exceptions": exceptions, "count": len(exceptions)})


# ---------------------------------------------------------------------------
# /api/transactions — read-only summary index for the Transaction Explorer
# ---------------------------------------------------------------------------

@app.route("/api/transactions")
def api_transactions():
    """Read-only index of every transaction result (any tier).

    Derived entirely from the already-computed in-memory ``_index``; never
    consults ground truth and never mutates any result. Powers the Transaction
    Explorer (client-side search, filter and sort) and, for STAGE_3 split
    settlements, carries the settlement breakdown so the UI can show the
    Expected -> Actual -> Variance relationship directly.
    """
    rows = []
    for tid, entry in sorted(_index.items()):
        d = entry["data"]
        gw_id = (d.get("matched_records") or {}).get("gateway")
        rows.append({
            "transaction_id": tid,
            "tier": entry["tier"],
            "status": d.get("status"),
            "rule": d.get("rule"),
            "reason": d.get("reason"),
            "gateway_row": gw_id,
            "ledger_row": (d.get("matched_records") or {}).get("ledger"),
            "bank_row_ids": d.get("bank_row_ids", []),
            "amount": _gw_amount_by_source.get(gw_id) if gw_id else None,
            "llm_consulted": bool(d.get("llm_consulted")),
            "settlement": d.get("settlement"),
        })
    return jsonify({"transactions": rows, "count": len(rows)})


# ---------------------------------------------------------------------------
# /api/transaction/<id> — full detail for one transaction
# ---------------------------------------------------------------------------

@app.route("/api/transaction/<txn_id>")
def api_transaction(txn_id: str):
    txn_id = txn_id.upper()
    entry = _index.get(txn_id)
    if entry is None:
        return jsonify({"error": f"Transaction '{txn_id}' not found"}), 404
    return jsonify({
        "transaction_id": txn_id,
        "tier": entry["tier"],
        **entry["data"],
    })


@app.route("/api/transaction/<txn_id>/retry-llm", methods=["POST"])
def api_retry_llm(txn_id: str):
    """Retry Gemini for one existing AI-retry transaction only."""
    global _qa_agent

    txn_id = txn_id.upper()
    entry = _index.get(txn_id)
    if entry is None:
        return jsonify({"error": f"Transaction '{txn_id}' not found"}), 404
    # Tier guard: only a true TIER_3 entry may be retried here. A Stage 3
    # AI_RETRY_REQUIRED entry must go through /retry-stage3 — running Tier 3
    # on a split transaction would overwrite its Stage 3 disposition.
    if entry["tier"] != "TIER_3" or entry["data"].get("status") != STATUS_AI_RETRY_REQUIRED:
        return jsonify({
            "error": "Only TIER_3 AI_RETRY_REQUIRED transactions can be retried via /retry-llm",
            "transaction_id": txn_id,
            "tier": entry["tier"],
            "status": entry["data"].get("status"),
        }), 409

    # Seed the retry with every bank row already claimed by other Tier 1/2/3
    # matches and by Stage 3 split Matches, so this retry can never re-offer
    # a row another result has consumed (global one-to-one uniqueness).
    result = retry_tier3_transaction(
        txn_id,
        _r2,
        _matcher,
        GeminiLLMClient(),
        already_consumed=_consumed_bank_ids(_r1, _r2, _r3) | _stage3_consumed,
    )
    result_data = result.to_dict()
    for index, previous in enumerate(_r3):
        if previous.transaction_id == txn_id:
            _r3[index] = result
            break
    _index[txn_id] = {"tier": "TIER_3", "data": result_data}
    # Preserve Stage 3 results in the Q&A agent (like /retry-stage3 does).
    _qa_agent = build_qa_agent(
        _r1, _r2, _r3, _r4,
        use_llm_for_explanations=True,
    )

    response = {"transaction_id": txn_id, "tier": "TIER_3", **result_data}
    if result.status == STATUS_AI_RETRY_REQUIRED:
        return jsonify(response), 503
    return jsonify(response)


@app.route("/api/transaction/<txn_id>/retry-stage3", methods=["POST"])
def api_retry_stage3(txn_id: str):
    """Retry Gemini for one existing Stage 3 AI_RETRY_REQUIRED transaction only.

    Re-runs Stage 3's deterministic-then-LLM adjudication for this single
    transaction with a fresh Gemini client, against the current consumed
    bank-row state. Python stays authoritative for candidate availability,
    uniqueness and arithmetic; Gemini only adjudicates genuinely ambiguous
    combinations. The existing Tier 3 retry workflow is untouched.
    """
    global _qa_agent

    txn_id = txn_id.upper()
    entry = _index.get(txn_id)
    if entry is None:
        return jsonify({"error": f"Transaction '{txn_id}' not found"}), 404
    if entry["tier"] != "STAGE_3" or entry["data"].get("status") != SplitStatus.AI_RETRY_REQUIRED:
        return jsonify({
            "error": "Only Stage 3 AI_RETRY_REQUIRED transactions can be retried",
            "transaction_id": txn_id,
            "tier": entry["tier"],
            "status": entry["data"].get("status"),
        }), 409

    # Reconstruct the pending_txn from the Tier 3 residue (source of truth).
    pending_txn = None
    for r in _r3:
        if r.transaction_id == txn_id:
            pending_txn = {
                "transaction_id": r.transaction_id,
                "gateway_row_id": r.matched_records.get("gateway"),
                "ledger_row_id": r.matched_records.get("ledger"),
            }
            break
    if pending_txn is None:
        return jsonify({"error": f"No Tier 3 residue found for '{txn_id}'"}), 404

    result = retry_stage3_transaction(
        txn_id,
        pending_txn,
        _matcher.gateway_records,
        _matcher.bank_records,
        _matcher.ledger_records,
        _consumed_bank_ids(_r1, _r2, _r3),
        _stage3_consumed,
        GeminiLLMClient(),
    )
    result_data = result.to_dict()
    for i, previous in enumerate(_r4):
        if previous.transaction_id == txn_id:
            _r4[i] = result
            break
    _index[txn_id] = {"tier": "STAGE_3", "data": result_data}
    if result.status == SplitStatus.MATCH:
        for bank_id in result.bank_row_ids:
            _stage3_consumed.add(bank_id)
    _qa_agent = build_qa_agent(
        _r1, _r2, _r3, _r4,
        use_llm_for_explanations=True,
    )

    response = {"transaction_id": txn_id, "tier": "STAGE_3", **result_data}
    if result.status == SplitStatus.AI_RETRY_REQUIRED:
        return jsonify(response), 503
    return jsonify(response)


@app.route("/api/transaction/<txn_id>/ai-review", methods=["POST"])
def api_ai_review(txn_id: str):
    """Return a read-only Gemini assessment of the stored transaction context."""
    txn_id = txn_id.upper()
    entry = _index.get(txn_id)
    if entry is None:
        return jsonify({"error": f"Transaction '{txn_id}' not found"}), 404

    data = entry["data"]
    context = {
        "transaction_id": txn_id,
        "tier": entry["tier"],
        "status": data.get("status"),
        "rule": data.get("rule"),
        "reason": data.get("reason"),
        "matched_records": data.get("matched_records", {}),
        "bank_row_ids": data.get("bank_row_ids", []),
        "evidence": data.get("evidence", {}),
        "settlement": data.get("settlement"),
    }
    system = (
        "You are a read-only payment reconciliation reviewer. Analyze only the "
        "provided transaction context. Do not change its status, select new rows, "
        "or invent financial facts. Respond as JSON with decision, confidence "
        "(0.0 to 1.0), rationale, evidence, and adjustment."
    )
    user = json.dumps({"transaction_context": context}, default=str)
    try:
        raw = GeminiFallbackClient(structured=False).complete(system, user)
        review = LLMAdjudicator._parse_llm_json(raw)
        if not isinstance(review, dict):
            return jsonify({"error": "Gemini returned an invalid AI review", "transaction_id": txn_id}), 422
        confidence = review.get("confidence")
        if isinstance(confidence, str):
            try:
                confidence = float(confidence.strip())
            except ValueError:
                confidence = None
        if isinstance(confidence, bool) or (
            confidence is not None
            and (not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0)
        ):
            confidence = None
        review = {
            "decision": str(review.get("decision") or "REVIEW"),
            "confidence": confidence,
            "rationale": str(review.get("rationale") or "No rationale returned by Gemini."),
            "evidence": review.get("evidence") if isinstance(review.get("evidence"), dict) else {},
            "adjustment": review.get("adjustment") if isinstance(review.get("adjustment"), dict) else {},
        }
    except Exception:
        status = data.get("status")
        deterministic_decision = "MATCH" if status in ("MATCH", "MATCHED") else "HUMAN_REVIEW"
        review = {
            "decision": deterministic_decision,
            "confidence": None,
            "rationale": (
                "Gemini was unavailable. This read-only review uses the stored "
                "pipeline result and does not make a new matching decision."
            ),
            "evidence": {
                "source": "stored_pipeline_context",
                "status": status,
                "rule": data.get("rule"),
                "reason": data.get("reason"),
            },
            "adjustment": {},
        }
        return jsonify({
            "transaction_id": txn_id,
            "review": review,
            "source_status": status,
            "source_tier": entry["tier"],
            "source": "DETERMINISTIC_FALLBACK",
            "llm_available": False,
        })

    return jsonify({
        "transaction_id": txn_id,
        "review": review,
        "source_status": data.get("status"),
        "source_tier": entry["tier"],
    })


# ---------------------------------------------------------------------------
# /api/qa — Q&A via the existing SettlementQAAgent
# ---------------------------------------------------------------------------

@app.route("/api/qa", methods=["POST"])
def api_qa():
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Missing 'question' field"}), 400

    answer = _qa_agent.ask(question)
    return jsonify(answer.to_dict())


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting LedgerLoop Controller UI on http://localhost:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
