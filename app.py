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
    GeminiLLMClient,
    STATUS_MATCH,
    STATUS_HUMAN_REVIEW,
    STATUS_UNRESOLVED,
)
from core.qa_agent import build_qa_agent

# ---------------------------------------------------------------------------
# Pipeline — run once at module load so the server starts hot
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _run_pipeline():
    """Execute the full reconciliation pipeline and return all results."""
    r1, summary1, matcher = run_tier1(data_dir=_DATA_DIR, return_matcher=True)
    residue1 = get_residue(r1)
    r2, summary2 = run_tier2(residue1, matcher)
    r3, summary3 = run_tier3(r2, matcher)   # uses env LLM_PROVIDER / GEMINI_API_KEY if set
    return r1, summary1, r2, summary2, r3, summary3, matcher


print("LedgerLoop: running reconciliation pipeline…", flush=True)
_r1, _summary1, _r2, _summary2, _r3, _summary3, _matcher = _run_pipeline()
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

# ---------------------------------------------------------------------------
# Build the authoritative result index for per-transaction lookups.
# Priority: Tier 3 > Tier 2 (matched) > Tier 1.
# ---------------------------------------------------------------------------

_index: dict[str, dict] = {}

for r in _r1:
    _index[r.transaction_id] = {"tier": "TIER_1", "data": r.to_dict()}

for r in _r2:
    if r.status == "MATCHED":
        _index[r.transaction_id] = {"tier": "TIER_2", "data": r.to_dict()}

for r in _r3:
    _index[r.transaction_id] = {"tier": "TIER_3", "data": r.to_dict()}

# ---------------------------------------------------------------------------
# Settlement Q&A agent (read-only wrapper over pipeline results)
# ---------------------------------------------------------------------------

_qa_agent = build_qa_agent(
    _r1, _r2, _r3,
    use_llm_for_explanations=False,   # deterministic answers only; prose LLM off by default
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

    return jsonify({
        "total_transactions": total,
        "status_counts": status_counts,
        "tier_counts": tier_counts,
        "rule_counts": rule_counts,
        "tier1_summary": t1,
        "tier2_summary": t2,
        "tier3_summary": t3,
        "llm_calls_made": t3["llm_calls_made"],
        "llm_recommendations_validated": t3["llm_recommendations_validated"],
        "llm_recommendations_rejected": t3["llm_recommendations_rejected"],
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
        if status in (STATUS_HUMAN_REVIEW, STATUS_UNRESOLVED):
            exceptions.append({
                "transaction_id": tid,
                "tier": entry["tier"],
                "status": status,
                "rule": d.get("rule"),
                "reason": d.get("reason"),
                "matched_records": d.get("matched_records", {}),
                "evidence": d.get("evidence", {}),
                "llm_consulted": d.get("llm_consulted", False),
            })
    return jsonify({"exceptions": exceptions, "count": len(exceptions)})


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
