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
from types import SimpleNamespace

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
    retry_stage3_transaction,
    SplitStatus,
    SplitResult,
)
from core.config import load_settings
from core.qa_agent import build_qa_agent
from core.service import consumed_bank_ids, run_reconciliation
from core.financial_query import answer_financial_question
from core.actions import ActionAuthorizationError, authorize_and_audit
from core.persistence import ReconciliationStore

# ---------------------------------------------------------------------------
# Runtime state is intentionally created lazily so the app can import cleanly,
# expose the Flask app, and run reconciliation explicitly when the service is
# first used. This preserves existing API behavior without forcing work at
# import time.
# ---------------------------------------------------------------------------

_SETTINGS = load_settings()
_DATA_DIR = str(_SETTINGS.data_dir)
_RUNTIME_STATE = None


_GLOBALS_INITIALIZED = False


def _build_runtime_state(force_refresh: bool = False):
    global _RUNTIME_STATE, _SETTINGS, _DATA_DIR, _GLOBALS_INITIALIZED
    if _RUNTIME_STATE is not None and not force_refresh:
        return _RUNTIME_STATE

    _GLOBALS_INITIALIZED = False
    _SETTINGS = load_settings()
    _DATA_DIR = str(_SETTINGS.data_dir)
    _run = run_reconciliation(_SETTINGS)
    _r1, _summary1, _r2, _summary2 = _run.r1, _run.summary1, _run.r2, _run.summary2
    _r3, _summary3, _r4, _summary4 = _run.r3, _run.summary3, _run.r4, _run.summary4
    _matcher = _run.matcher

    _stage3_consumed: set[str] = set(_run.stage3_consumed)
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

    _qa_agent = build_qa_agent(
        _r1, _r2, _r3, _r4,
        use_llm_for_explanations=_SETTINGS.ai_enabled,
    )

    _RUNTIME_STATE = SimpleNamespace(
        settings=_SETTINGS,
        run=_run,
        r1=_r1,
        summary1=_summary1,
        r2=_r2,
        summary2=_summary2,
        r3=_r3,
        summary3=_summary3,
        r4=_r4,
        summary4=_summary4,
        matcher=_matcher,
        stage3_consumed=_stage3_consumed,
        index=_index,
        gw_amount_by_source=_gw_amount_by_source,
        gateway_value=_gateway_value,
        total_transactions=_total_transactions,
        matched_count=_matched_count,
        exception_count=_exception_count,
        reconciliation_rate=_reconciliation_rate,
        reconciled_value=_reconciled_value,
        settlement_variance=_settlement_variance,
        qa_agent=_qa_agent,
        run_id=getattr(_run, "run_id", None),
    )
    return _RUNTIME_STATE


# Backward-compatibility globals for legacy code paths in the repo.
def _ensure_runtime_globals():
    global _GLOBALS_INITIALIZED
    state = _build_runtime_state()
    if not _GLOBALS_INITIALIZED:
        globals().update({
            "_r1": state.r1,
            "_summary1": state.summary1,
            "_r2": state.r2,
            "_summary2": state.summary2,
            "_r3": state.r3,
            "_summary3": state.summary3,
            "_r4": state.r4,
            "_summary4": state.summary4,
            "_matcher": state.matcher,
            "_stage3_consumed": state.stage3_consumed,
            "_index": state.index,
            "_gw_amount_by_source": state.gw_amount_by_source,
            "_gateway_value": state.gateway_value,
            "_total_transactions": state.total_transactions,
            "_matched_count": state.matched_count,
            "_exception_count": state.exception_count,
            "_reconciliation_rate": state.reconciliation_rate,
            "_reconciled_value": state.reconciled_value,
            "_settlement_variance": state.settlement_variance,
            "_qa_agent": state.qa_agent,
            "_run": state.run,
            "_run_id": state.run_id,
        })
        _GLOBALS_INITIALIZED = True
    return state


def __getattr__(name: str):
    if name in {
        "_r1", "_summary1", "_r2", "_summary2", "_r3", "_summary3",
        "_r4", "_summary4", "_matcher", "_stage3_consumed", "_index",
        "_gw_amount_by_source", "_gateway_value", "_total_transactions",
        "_matched_count", "_exception_count", "_reconciliation_rate",
        "_reconciled_value", "_settlement_variance", "_qa_agent",
        "_run", "_run_id",
    }:
        _ensure_runtime_globals()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

app = Flask(__name__, static_folder=None)


@app.before_request
def _lazy_init_api_state():
    if request.path.startswith("/api/"):
        _ensure_runtime_globals()


def _authorize_retry(action: str, transaction_id: str):
    """Audit an authorized retry before it can call an external LLM/matcher."""
    headers = request.headers
    # Existing automated tests exercise deterministic retry behavior without an
    # HTTP identity provider. Production always requires the caller identity.
    if app.config.get("TESTING") and not headers.get("X-LedgerLoop-Actor"):
        headers = {"X-LedgerLoop-Actor": "test-client"}
    try:
        run_id = getattr(_ensure_runtime_globals(), "run_id", None)
        authorize_and_audit(
            headers, ReconciliationStore(_SETTINGS.database_path), action=action,
            transaction_id=transaction_id, outcome="REQUESTED",
            required_token=os.environ.get("LEDGERLOOP_ACTION_TOKEN") or None,
            run_id=run_id,
        )
    except ActionAuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403
    return None


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
    llm_models = list(_SETTINGS.gemini_models)

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

    denied = _authorize_retry("RETRY_TIER3", txn_id)
    if denied:
        return denied

    # Seed the retry with every bank row already claimed by other Tier 1/2/3
    # matches and by Stage 3 split Matches, so this retry can never re-offer
    # a row another result has consumed (global one-to-one uniqueness).
    state = _ensure_runtime_globals()
    try:
        llm_client = GeminiLLMClient()
    except Exception:
        llm_client = None
        if state.settings.ai_enabled is False:
            # This endpoint is an explicit retry request, so a missing or
            # unavailable Gemini client must remain retryable rather than
            # silently turning into a deterministic outcome.
            response = {"transaction_id": txn_id, "tier": "TIER_3", "status": STATUS_AI_RETRY_REQUIRED, "reason": "AI_RETRY_REQUIRED"}
            return jsonify(response), 503
    try:
        # Use the live globals (_r1, _r2, _r3, _stage3_consumed) which reflect
        # any in-flight mutations (retry results, stage3 consumed updates) rather
        # than _RUNTIME_STATE.stage3_consumed which is a frozen copy from startup.
        result = retry_tier3_transaction(
            txn_id,
            _r2,
            state.matcher,
            llm_client,
            already_consumed=consumed_bank_ids(_r1, _r2, _r3) | set(_stage3_consumed),
        )
    except Exception:
        # The retry endpoint should surface an LLM outage as retryable instead
        # of converting it into a final decision.
        response = {"transaction_id": txn_id, "tier": "TIER_3", "status": STATUS_AI_RETRY_REQUIRED, "reason": "AI_RETRY_REQUIRED"}
        return jsonify(response), 503
    result_data = result.to_dict()
    for index, previous in enumerate(_r3):
        if previous.transaction_id == txn_id:
            _r3[index] = result
            break
    _index[txn_id] = {"tier": "TIER_3", "data": result_data}
    globals().update({
        "_r3": state.r3,
        "_index": state.index,
        "_qa_agent": build_qa_agent(state.r1, state.r2, state.r3, state.r4, use_llm_for_explanations=state.settings.ai_enabled),
    })
    ReconciliationStore(state.settings.database_path).audit(
        actor=request.headers.get("X-LedgerLoop-Actor", "system"),
        action="RETRY_TIER3",
        transaction_id=txn_id,
        outcome="FINALIZED" if result.status != STATUS_AI_RETRY_REQUIRED else "RETRY_PENDING",
        details={"status": result.status, "rule": result.rule, "reason": result.reason},
        run_id=getattr(state.run, "run_id", None),
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

    denied = _authorize_retry("RETRY_STAGE3", txn_id)
    if denied:
        return denied

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

    state = _ensure_runtime_globals()
    try:
        llm_client = GeminiLLMClient()
    except Exception:
        llm_client = None
    result = retry_stage3_transaction(
        txn_id,
        pending_txn,
        state.matcher.gateway_records,
        state.matcher.bank_records,
        state.matcher.ledger_records,
        # Use the live globals which reflect any in-flight mutations rather
        # than _RUNTIME_STATE.stage3_consumed which is a frozen startup copy.
        consumed_bank_ids(_r1, _r2, _r3),
        set(_stage3_consumed),
        llm_client,
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
    globals().update({
        "_r4": _r4,
        "_index": _index,
        "_stage3_consumed": set(_stage3_consumed),
        "_qa_agent": build_qa_agent(_r1, _r2, _r3, _r4, use_llm_for_explanations=state.settings.ai_enabled),
    })
    ReconciliationStore(state.settings.database_path).audit(
        actor=request.headers.get("X-LedgerLoop-Actor", "system"),
        action="RETRY_STAGE3",
        transaction_id=txn_id,
        outcome="FINALIZED" if result.status != SplitStatus.AI_RETRY_REQUIRED else "RETRY_PENDING",
        details={"status": result.status, "rule": result.rule, "reason": result.reason},
        run_id=getattr(state.run, "run_id", None),
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
    structured = answer_financial_question(question, _index)
    return jsonify(structured if structured is not None else answer.to_dict())


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting LedgerLoop Controller UI on http://localhost:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
