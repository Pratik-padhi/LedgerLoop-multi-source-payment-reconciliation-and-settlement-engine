"""
LedgerLoop — Settlement Q&A Agent
===================================

A BOUNDED, READ-ONLY question-answering layer over the completed reconciliation
results produced by Tiers 1, 2, and 3.  It does NOT re-run or alter any
reconciliation logic; it only retrieves and explains what the pipeline already
decided.

DESIGN PRINCIPLES
-----------------
1. Deterministic retrieval FIRST.  Every answer is grounded in structured
   lookups against the in-memory result index built from the pipeline output.
   Gemini is consulted ONLY when a question cannot be answered by a plain
   lookup and a user-facing prose explanation would be genuinely more helpful
   than a raw JSON dump.

2. Read-only safety.  The agent NEVER modifies a Tier1Result, Tier2Result, or
   Tier3Result object.  It has no write path to the data at all.

3. No hallucination path.  If a transaction is not found in the index, the
   agent returns "not found" immediately — it never invents a transaction,
   status, amount, source ID, or evidence field.

4. Bounded LLM scope.  When Gemini IS used, it receives ONLY the structured
   data already retrieved for the specific question.  It NEVER sees the full
   dataset, never makes a reconciliation decision, and its output is returned
   verbatim as an "explanation" string — not interpreted as a structured
   command.

5. Status semantics preserved.  MATCHED / HUMAN_REVIEW / UNRESOLVED (Tier 3)
   and MATCHED / PARTIAL_MATCH / UNRESOLVED_FOR_TIER_1 (Tier 1) labels are
   surfaced exactly as the pipeline produced them — the agent never maps,
   relabels, or conflates them.

SUPPORTED QUESTION INTENTS
---------------------------
    LOOKUP          "What happened to PAY109?"
    STATUS          "What is the status of PAY109?"
    WHY             "Why is PAY109 matched?"
    EVIDENCE        "What evidence supports PAY109?"
    FILTER_STATUS   "Which transactions need human review?"
                    "Show me unresolved transactions."
    FILTER_RULE     "Which transactions were matched by the LLM-assisted
                       split settlement rule?"
    UNSUPPORTED     Anything outside the above set → explicit refusal, never
                    a guess.

STRICT ARCHITECTURAL BOUNDARY
-------------------------------
This module DOES:
    - index Tier 1 / 2 / 3 results in memory (read-only)
    - answer the closed set of question intents listed above
    - retrieve only the records relevant to the specific question
    - compose a structured QAAnswer for deterministic questions
    - optionally ask Gemini to write a prose explanation from retrieved data
    - return "not found" for unknown transaction IDs
    - return "unsupported" for out-of-scope questions

This module DOES NOT:
    - modify any reconciliation result
    - invent transactions, IDs, amounts, or evidence
    - run a second reconciliation engine
    - call Gemini over the full dataset
    - accept Gemini's output as a structured answer (prose only)
    - expose API keys
    - answer questions that require running a new pipeline pass
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Importing only the result / status types we need from existing modules.
# We import NO matching logic — only the dataclasses and constants.
# ---------------------------------------------------------------------------
from core.match_exact import (
    Tier1Result,
    STATUS_MATCHED as T1_MATCHED,
    STATUS_PARTIAL_MATCH as T1_PARTIAL,
    STATUS_UNRESOLVED_FOR_TIER_1 as T1_UNRESOLVED,
)
from core.match_fuzzy import (
    Tier2Result,
    STATUS_MATCHED as T2_MATCHED,
)
from core.match_llm import (
    Tier3Result,
    STATUS_MATCH as T3_MATCH,
    STATUS_HUMAN_REVIEW as T3_HUMAN_REVIEW,
    STATUS_UNRESOLVED as T3_UNRESOLVED,
    RULE_SPLIT_SETTLEMENT_SUM,
    RULE_REFUND_LINKED_NET_AMOUNT,
    RULE_TDS_LINKED_NET_AMOUNT,
    RULE_DESCRIPTION_LINKED_REFERENCE,
    GeminiLLMClient,
    LLMUnavailableError,
)
from core.match_split import (
    SplitResult,
    SplitStatus,
)


# ===========================================================================
# Public status constants (mirrors match_llm's taxonomy for callers)
# ===========================================================================

QA_STATUS_MATCHED = T3_MATCH
QA_STATUS_HUMAN_REVIEW = T3_HUMAN_REVIEW
QA_STATUS_UNRESOLVED = T3_UNRESOLVED

# Human-readable rule labels used in answers
_RULE_LABELS: dict[str, str] = {
    RULE_REFUND_LINKED_NET_AMOUNT: "refund-linked net amount",
    RULE_TDS_LINKED_NET_AMOUNT: "TDS-linked net amount",
    RULE_DESCRIPTION_LINKED_REFERENCE: "description-linked reference",
    RULE_SPLIT_SETTLEMENT_SUM: "LLM-assisted split settlement",
    # Tier 1 / 2 rules
    "EXACT_REFERENCE_AND_AMOUNT": "exact reference and amount (Tier 1)",
    "EXACT_GATEWAY_REFERENCE_AND_AMOUNT": "exact gateway reference and amount (Tier 1)",
    "PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE": "reference + amount within tolerance (Tier 2)",
}

# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------

INTENT_LOOKUP = "LOOKUP"
INTENT_STATUS = "STATUS"
INTENT_WHY = "WHY"
INTENT_EVIDENCE = "EVIDENCE"
INTENT_FILTER_STATUS = "FILTER_STATUS"
INTENT_FILTER_RULE = "FILTER_RULE"
INTENT_UNSUPPORTED = "UNSUPPORTED"

# ---------------------------------------------------------------------------
# Answer dataclass
# ---------------------------------------------------------------------------


@dataclass
class QAAnswer:
    """
    Structured answer returned by the Q&A agent.

    All fields are populated from retrieved data only — never invented.
    `explanation` may be LLM-composed prose, but only when `llm_used` is True,
    and its content is always grounded in `retrieved_data`.
    """
    intent: str                        # which INTENT_* constant was matched
    question: str                      # the original question, echoed back
    found: bool                        # False → transaction not in index
    supported: bool                    # False → question out of supported scope
    transaction_ids: list[str]         # transactions the answer is about
    retrieved_data: list[dict]         # raw structured data that grounds the answer
    explanation: Optional[str]         # human-readable prose (LLM or template)
    llm_used: bool                     # whether Gemini was consulted
    llm_unavailable: bool              # True if Gemini was needed but missing/failed

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# Result index — built once from the full pipeline output
# ===========================================================================


class ReconciliationIndex:
    """
    Immutable (after construction) in-memory index of all pipeline results.

    Built from the raw lists returned by run_tier1 / run_tier2 / run_tier3.
    The agent queries this index; it never touches the pipeline modules.

    Tier priority for per-transaction lookup:
        Tier 3 > Tier 2 (matched) > Tier 1 (matched)

    For a given transaction_id, we expose the HIGHEST-tier result that has
    data for it:
        - If Tier 3 processed it, that result is authoritative.
        - If Tier 2 MATCHED it (and Tier 3 didn't process it), Tier 2 is used.
        - If only Tier 1 resolved it, Tier 1 is used.
    """

    def __init__(
        self,
        tier1_results: list[Tier1Result],
        tier2_results: list[Tier2Result],
        tier3_results: list[Tier3Result],
        stage3_results: Optional[list[SplitResult]] = None,
    ):
        # Index each tier independently so the agent can answer tier-specific
        # filter questions (e.g. "which transactions are HUMAN_REVIEW").
        self._t1: dict[str, Tier1Result] = {r.transaction_id: r for r in tier1_results}
        self._t2: dict[str, Tier2Result] = {r.transaction_id: r for r in tier2_results}
        self._t3: dict[str, Tier3Result] = {r.transaction_id: r for r in tier3_results}
        self._s3: dict[str, SplitResult] = {
            r.transaction_id: r for r in (stage3_results or [])
        }

        # Build a flat authoritative view: transaction_id → best result dict
        # (serialised to plain dict so we never mutate the originals).
        # Priority: Stage 3 > Tier 3 > Tier 2 (matched) > Tier 1 (matched).
        # Stage 3 is the split / multi-payment / partial pass that only runs on
        # Tier 3 residue, so its decision is authoritative over Tier 3 for those
        # transactions it evaluated.
        self._authoritative: dict[str, dict] = {}
        for r in tier1_results:
            self._authoritative[r.transaction_id] = {"tier": "TIER_1", "data": r.to_dict()}
        for r in tier2_results:
            if r.status == T2_MATCHED:
                self._authoritative[r.transaction_id] = {"tier": "TIER_2", "data": r.to_dict()}
        for r in tier3_results:
            self._authoritative[r.transaction_id] = {"tier": "TIER_3", "data": r.to_dict()}
        for r in stage3_results or []:
            self._authoritative[r.transaction_id] = {"tier": "STAGE_3", "data": r.to_dict()}

        # Rule → transaction_id list (for filter-by-rule queries)
        self._by_rule: dict[str, list[str]] = {}
        for r in tier1_results:
            if r.rule:
                self._by_rule.setdefault(r.rule, []).append(r.transaction_id)
        for r in tier2_results:
            if r.rule:
                self._by_rule.setdefault(r.rule, []).append(r.transaction_id)
        for r in tier3_results:
            if r.rule:
                self._by_rule.setdefault(r.rule, []).append(r.transaction_id)
        for r in stage3_results or []:
            if r.rule:
                self._by_rule.setdefault(r.rule, []).append(r.transaction_id)

    # -----------------------------------------------------------------------
    # Lookup
    # -----------------------------------------------------------------------

    def get(self, transaction_id: str) -> Optional[dict]:
        """Return the authoritative result dict for a transaction, or None."""
        return self._authoritative.get(transaction_id)

    def all_transaction_ids(self) -> list[str]:
        return sorted(self._authoritative.keys())

    # -----------------------------------------------------------------------
    # Status filters (operate over Tier 3 results primarily; fall back to
    # the authoritative tier for transactions Tier 3 didn't process)
    # -----------------------------------------------------------------------

    def filter_by_status(self, status: str) -> list[dict]:
        """
        Return all authoritative result dicts whose effective status matches.
        Status is read from the highest-tier result for each transaction.
        """
        out = []
        for tid, entry in sorted(self._authoritative.items()):
            d = entry["data"]
            if d.get("status") == status:
                out.append({"transaction_id": tid, "tier": entry["tier"], **d})
        return out

    def filter_by_rule(self, rule: str) -> list[dict]:
        """
        Return all authoritative result dicts whose rule matches exactly.
        """
        ids = self._by_rule.get(rule, [])
        results = []
        for tid in sorted(ids):
            entry = self._authoritative.get(tid)
            if entry:
                results.append({"transaction_id": tid, "tier": entry["tier"], **entry["data"]})
        return results

    def summary_counts(self) -> dict:
        """Aggregate status counts across all authoritative results."""
        counts: dict[str, int] = {}
        for entry in self._authoritative.values():
            s = entry["data"].get("status", "UNKNOWN")
            counts[s] = counts.get(s, 0) + 1
        return counts


# ===========================================================================
# Intent classifier — deterministic keyword / regex approach
# ===========================================================================

# Patterns for extracting a transaction ID (PAY\d+, with optional trailing
# letter for Stage 3 split sub-rows like PAY107B, and optional -REFUND suffix)
_TXN_ID_RE = re.compile(r"\b(PAY\d+[A-Z]?(?:-REFUND)?)\b", re.IGNORECASE)

# Rule keywords mapped to canonical rule constants
_RULE_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"split\s+settlement", re.IGNORECASE), RULE_SPLIT_SETTLEMENT_SUM),
    (re.compile(r"llm[- ]assisted", re.IGNORECASE), RULE_SPLIT_SETTLEMENT_SUM),
    (re.compile(r"refund[- ]linked", re.IGNORECASE), RULE_REFUND_LINKED_NET_AMOUNT),
    (re.compile(r"tds[- ]linked", re.IGNORECASE), RULE_TDS_LINKED_NET_AMOUNT),
    (re.compile(r"description[- ]linked", re.IGNORECASE), RULE_DESCRIPTION_LINKED_REFERENCE),
    (re.compile(r"tax[- ]line", re.IGNORECASE), RULE_TDS_LINKED_NET_AMOUNT),
    (re.compile(r"\btds\b", re.IGNORECASE), RULE_TDS_LINKED_NET_AMOUNT),
]

# Status keywords mapped to canonical status values
_STATUS_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"human[- ]review", re.IGNORECASE), T3_HUMAN_REVIEW),
    (re.compile(r"need[s]?\s+(?:human|review|manual)", re.IGNORECASE), T3_HUMAN_REVIEW),
    (re.compile(r"unresolv", re.IGNORECASE), T3_UNRESOLVED),
    (re.compile(r"\bmatched?\b", re.IGNORECASE), T3_MATCH),
]


def _extract_transaction_id(question: str) -> Optional[str]:
    """Extract the first PAY-style transaction ID from the question, uppercased."""
    m = _TXN_ID_RE.search(question)
    return m.group(1).upper() if m else None


def _extract_rule(question: str) -> Optional[str]:
    for pattern, rule in _RULE_KEYWORDS:
        if pattern.search(question):
            return rule
    return None


def _extract_filter_status(question: str) -> Optional[str]:
    for pattern, status in _STATUS_KEYWORDS:
        if pattern.search(question):
            return status
    return None


def classify_intent(question: str) -> tuple[str, dict]:
    """
    Classify the question into one of the supported intents.

    Returns (intent, extras) where extras holds extracted parameters
    (transaction_id, rule, status) for the downstream handler.
    """
    q = question.strip()
    if not q:
        return INTENT_UNSUPPORTED, {}

    txn_id = _extract_transaction_id(q)

    # --- Intent: filter by rule (no specific transaction) ---
    rule = _extract_rule(q)
    if rule and not txn_id:
        return INTENT_FILTER_RULE, {"rule": rule}

    # --- Intent: filter by status (no specific transaction) ---
    # Detect list/filter framing without a specific transaction ID
    _list_framing = re.search(
        r"(which|list|show|all|give|get|find|display|what\s+are)", q, re.IGNORECASE
    )
    if _list_framing and not txn_id:
        status = _extract_filter_status(q)
        if status:
            return INTENT_FILTER_STATUS, {"status": status}

    # --- Transaction-specific intents ---
    if txn_id:
        # WHY: why matched / why unresolved / why human review
        if re.search(r"\bwhy\b", q, re.IGNORECASE):
            return INTENT_WHY, {"transaction_id": txn_id}

        # EVIDENCE: evidence / support / proof
        if re.search(r"\b(evidence|support|proof|backing)\b", q, re.IGNORECASE):
            return INTENT_EVIDENCE, {"transaction_id": txn_id}

        # STATUS: status / state / reconciliation status
        if re.search(
            r"\b(status|state|reconcil|what\s+is|tell\s+me)\b", q, re.IGNORECASE
        ):
            return INTENT_STATUS, {"transaction_id": txn_id}

        # LOOKUP: catch-all "what happened to", "show me", "tell me about"
        return INTENT_LOOKUP, {"transaction_id": txn_id}

    # --- Nothing matched ---
    return INTENT_UNSUPPORTED, {}


# ===========================================================================
# Answer composers (deterministic, no LLM)
# ===========================================================================

def _format_rule(rule: Optional[str]) -> str:
    if not rule:
        return "none"
    return _RULE_LABELS.get(rule, rule)


def _is_stage3(d: dict) -> bool:
    """Detect a Stage 3 (split / multi-payment) result dict by its shape."""
    return "bank_row_ids" in d and "settlement" in d


def _format_money(value) -> str:
    """Format a monetary field for a human-readable line (INR, 2 dp)."""
    if value is None:
        return "—"
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _stage3_summary_lines(d: dict) -> list[str]:
    """Human-readable lines specific to a Stage 3 split/multi-payment result."""
    lines: list[str] = []
    bank_ids = d.get("bank_row_ids") or []
    lines.append(f"Bank row(s): {', '.join(bank_ids) if bank_ids else '(none)'}")
    if d.get("received") is not None:
        lines.append(f"Received: {_format_money(d.get('received'))}")
    if d.get("outstanding") is not None:
        lines.append(f"Outstanding: {_format_money(d.get('outstanding'))}")
    if d.get("confidence") is not None:
        lines.append(f"Confidence: {d.get('confidence')}")
    settlement = d.get("settlement") or {}
    if settlement:
        lines.append(
            "Settlement: "
            f"gross={_format_money(settlement.get('gross_amount'))} "
            f"gst={_format_money(settlement.get('gst_amount'))} "
            f"tds={_format_money(settlement.get('tds_amount'))} "
            f"fees={_format_money(settlement.get('total_fee_amount'))} "
            f"expected_net={_format_money(settlement.get('expected_net_amount'))} "
            f"actual_bank={_format_money(settlement.get('actual_bank_amount'))}"
        )
    return lines


def _compose_lookup_answer(txn_id: str, entry: dict) -> str:
    """Plain-text summary of everything we know about a transaction."""
    d = entry["data"]
    tier = entry["tier"]
    status = d.get("status", "UNKNOWN")
    rule = _format_rule(d.get("rule"))
    reason = d.get("reason") or "—"
    matched = d.get("matched_records", {})
    evidence = d.get("evidence", {})
    llm_consulted = d.get("llm_consulted", False)

    lines = [
        f"Transaction: {txn_id}",
        f"Resolved at: {tier}",
        f"Status:      {status}",
        f"Rule:        {rule}",
        f"Reason:      {reason}",
    ]
    if _is_stage3(d):
        # Split / multi-payment / partial shape: bank rows + settlement.
        lines.append(f"Matched records: gateway={d.get('gateway_row_id')}, "
                     f"ledger={d.get('ledger_row_id') or '—'}")
        lines.extend(_stage3_summary_lines(d))
    else:
        lines.append(
            "Matched records: "
            + ", ".join(f"{k}={v}" for k, v in matched.items() if v)
        )
    if evidence:
        ev_parts = []
        for k, v in evidence.items():
            if v is not None:
                ev_parts.append(f"{k}={v}")
        lines.append("Evidence: " + "; ".join(ev_parts))
    if llm_consulted:
        lines.append("LLM consulted: yes (split-settlement adjudication)")
    return "\n".join(lines)


def _compose_why_answer(txn_id: str, entry: dict) -> str:
    d = entry["data"]
    status = d.get("status", "UNKNOWN")
    rule = _format_rule(d.get("rule"))
    reason = d.get("reason") or "—"
    evidence = d.get("evidence", {})

    if _is_stage3(d):
        explanation = f"{txn_id} is {status} (Stage 3 split/multi-payment pass) via rule: {rule}."
        explanation += f"  Reason: {reason}."
        if status == SplitStatus.MATCH:
            bank_ids = ", ".join(d.get("bank_row_ids") or [])
            explanation += f"  It is settled by bank row(s): {bank_ids}."
        elif status == SplitStatus.PARTIAL:
            explanation += (
                f"  Received {_format_money(d.get('received'))} of "
                f"{_format_money(d.get('expected_net'))} expected; "
                f"outstanding {_format_money(d.get('outstanding'))}."
            )
        if d.get("confidence") is not None:
            explanation += f"  Confidence: {d.get('confidence')}."
        return explanation

    if status == T3_MATCH:
        explanation = f"PAY{txn_id.lstrip('PAY')} was matched" if txn_id.startswith("PAY") else f"{txn_id} was matched"
        explanation = f"{txn_id} was matched via rule: {rule}."
        if evidence:
            ev_str = "; ".join(f"{k}={v}" for k, v in evidence.items() if v is not None)
            explanation += f"  Evidence: {ev_str}."
        if d.get("llm_consulted"):
            explanation += "  Gemini was consulted to identify the split-settlement combination; the arithmetic was independently validated in Python."
    elif status == T3_HUMAN_REVIEW:
        explanation = f"{txn_id} requires human review. Reason: {reason}."
        if evidence:
            ev_str = "; ".join(f"{k}={v}" for k, v in evidence.items() if v is not None)
            explanation += f"  Available evidence: {ev_str}."
    else:  # UNRESOLVED or Tier1/2 statuses
        explanation = f"{txn_id} is {status}. Reason: {reason}."
        if evidence:
            ev_str = "; ".join(f"{k}={v}" for k, v in evidence.items() if v is not None)
            explanation += f"  Context: {ev_str}."
    return explanation


def _compose_evidence_answer(txn_id: str, entry: dict) -> str:
    d = entry["data"]
    evidence = d.get("evidence", {})
    rule = _format_rule(d.get("rule"))
    matched = d.get("matched_records", {})
    llm_rec = d.get("llm_recommendation")

    if _is_stage3(d):
        lines = [f"Evidence for {txn_id} (rule: {rule}, status: {d.get('status')}):"]
        lines.extend(_stage3_summary_lines(d))
        for k, v in evidence.items():
            if v is not None:
                lines.append(f"  {k}: {v}")
        if d.get("llm_recommendation"):
            rec = d.get("llm_recommendation")
            lines.append(
                f"  LLM recommendation (for audit): decision={rec.get('decision')}, "
                f"bank_row_ids={rec.get('bank_row_ids')}"
            )
        return "\n".join(lines)

    if not evidence and not matched:
        return f"No structured evidence is recorded for {txn_id}."

    lines = [f"Evidence for {txn_id} (rule: {rule}):"]
    for k, v in evidence.items():
        if v is not None:
            lines.append(f"  {k}: {v}")
    if matched:
        lines.append("Matched source rows:")
        for src, row_id in matched.items():
            if row_id:
                lines.append(f"  {src}: {row_id}")
    if llm_rec:
        lines.append(
            f"LLM recommendation (for audit): "
            f"decision={llm_rec.get('decision')}, "
            f"bank_row_ids={llm_rec.get('bank_row_ids')}"
        )
    return "\n".join(lines)


def _compose_filter_answer(status: str, entries: list[dict]) -> str:
    if not entries:
        return f"No transactions currently have status: {status}."
    ids = [e["transaction_id"] for e in entries]
    return (
        f"{len(ids)} transaction(s) with status {status}:\n  "
        + "\n  ".join(ids)
    )


def _compose_rule_filter_answer(rule: str, entries: list[dict]) -> str:
    label = _format_rule(rule)
    if not entries:
        return f"No transactions were matched by rule: {label}."
    ids = [e["transaction_id"] for e in entries]
    return (
        f"{len(ids)} transaction(s) matched via rule '{label}':\n  "
        + "\n  ".join(ids)
    )


# ===========================================================================
# Gemini composition helper (prose-only, bounded to retrieved data)
# ===========================================================================

def _compose_with_gemini(
    question: str,
    retrieved: list[dict],
    llm_client,
) -> tuple[str, bool]:
    """
    Ask Gemini to compose a human-readable prose explanation from
    `retrieved` data. Returns (prose, llm_used).

    If Gemini is unavailable, returns ("", False) — the caller falls back to
    the template-composed explanation.

    Safety invariants:
    - Only `retrieved` data (already extracted by the deterministic layer) is
      sent; the full dataset is never included.
    - Gemini's response is used verbatim as prose ONLY — it is never parsed as
      a structured command or reconciliation decision.
    - An empty or failed response silently falls back.
    """
    if llm_client is None:
        return "", False

    system = (
        "You are a payment-reconciliation assistant. "
        "You are given structured reconciliation data for one or more transactions. "
        "Your sole job is to write a clear, concise explanation of what happened "
        "to these transactions based ONLY on the data provided. "
        "Do NOT invent any transaction IDs, amounts, dates, or evidence. "
        "Do NOT make any reconciliation decisions. "
        "Respond in plain English, 3–6 sentences. No JSON, no bullet points."
    )
    user_payload = {
        "user_question": question,
        "reconciliation_data": retrieved,
    }

    try:
        prose = llm_client.complete(system, json.dumps(user_payload, default=str))
        return prose.strip(), True
    except LLMUnavailableError:
        return "", False
    except Exception:
        return "", False


# ===========================================================================
# Main Q&A agent
# ===========================================================================


class SettlementQAAgent:
    """
    Bounded Settlement Q&A agent.

    Usage:
        index = ReconciliationIndex(tier1_results, tier2_results, tier3_results)
        agent = SettlementQAAgent(index)
        answer = agent.ask("What happened to PAY109?")
        print(answer.explanation)

    The agent is stateless between calls (the index is the only shared state,
    and it is read-only).  It is safe to call `ask()` concurrently.
    """

    def __init__(
        self,
        index: ReconciliationIndex,
        llm_client=None,
        use_llm_for_explanations: bool = False,
    ):
        """
        index: pre-built ReconciliationIndex (read-only).
        llm_client: optional LLMClient for prose composition. If None, Gemini
            is auto-selected from the environment when
            use_llm_for_explanations=True.  Set to None and
            use_llm_for_explanations=False to disable all LLM use.
        use_llm_for_explanations: when True and a client is available, ask
            Gemini to compose a richer prose explanation for LOOKUP / WHY /
            EVIDENCE questions.  The deterministic answer is ALWAYS populated
            first; Gemini only provides an optional polish layer.
        """
        self._index = index
        self._use_llm = use_llm_for_explanations

        if llm_client is not None:
            self._llm = llm_client
        elif use_llm_for_explanations:
            # Auto-select Gemini from the environment (same logic as run_tier3)
            provider = os.environ.get("LLM_PROVIDER", "").lower()
            if provider == "gemini" or (not provider and os.environ.get("GEMINI_API_KEY")):
                self._llm = GeminiLLMClient()
            else:
                self._llm = None
        else:
            self._llm = None

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def ask(self, question: str) -> QAAnswer:
        """
        Answer a natural-language question about the reconciliation results.

        Returns a QAAnswer.  The `explanation` field is always populated for
        supported, found questions — either from a template or from Gemini.
        `found=False` when the transaction ID is not in the index.
        `supported=False` when the question is outside the supported scope.
        """
        intent, extras = classify_intent(question)

        if intent == INTENT_UNSUPPORTED:
            return self._unsupported_answer(question)

        if intent == INTENT_FILTER_STATUS:
            return self._handle_filter_status(question, extras["status"])

        if intent == INTENT_FILTER_RULE:
            return self._handle_filter_rule(question, extras["rule"])

        # Transaction-specific intents all need a transaction ID
        txn_id = extras.get("transaction_id")
        if not txn_id:
            return self._unsupported_answer(question)

        entry = self._index.get(txn_id)
        if entry is None:
            return QAAnswer(
                intent=intent,
                question=question,
                found=False,
                supported=True,
                transaction_ids=[txn_id],
                retrieved_data=[],
                explanation=f"Transaction '{txn_id}' was not found in the reconciliation results.",
                llm_used=False,
                llm_unavailable=False,
            )

        if intent == INTENT_LOOKUP:
            return self._handle_lookup(question, txn_id, entry)
        if intent == INTENT_STATUS:
            return self._handle_status(question, txn_id, entry)
        if intent == INTENT_WHY:
            return self._handle_why(question, txn_id, entry)
        if intent == INTENT_EVIDENCE:
            return self._handle_evidence(question, txn_id, entry)

        return self._unsupported_answer(question)

    # -----------------------------------------------------------------------
    # Per-intent handlers
    # -----------------------------------------------------------------------

    def _handle_lookup(self, question: str, txn_id: str, entry: dict) -> QAAnswer:
        base_explanation = _compose_lookup_answer(txn_id, entry)
        retrieved = [{"transaction_id": txn_id, **entry["data"]}]
        explanation, llm_used, llm_unavailable = self._maybe_compose_with_llm(
            question, retrieved, base_explanation
        )
        return QAAnswer(
            intent=INTENT_LOOKUP,
            question=question,
            found=True,
            supported=True,
            transaction_ids=[txn_id],
            retrieved_data=retrieved,
            explanation=explanation,
            llm_used=llm_used,
            llm_unavailable=llm_unavailable,
        )

    def _handle_status(self, question: str, txn_id: str, entry: dict) -> QAAnswer:
        d = entry["data"]
        status = d.get("status", "UNKNOWN")
        tier = entry["tier"]
        reason = d.get("reason")
        rule = d.get("rule")

        lines = [f"Status of {txn_id}: {status} (resolved at {tier})"]
        if rule:
            lines.append(f"Rule: {_format_rule(rule)}")
        if reason:
            lines.append(f"Reason: {reason}")

        retrieved = [{"transaction_id": txn_id, "status": status, "tier": tier,
                      "rule": rule, "reason": reason}]
        return QAAnswer(
            intent=INTENT_STATUS,
            question=question,
            found=True,
            supported=True,
            transaction_ids=[txn_id],
            retrieved_data=retrieved,
            explanation="\n".join(lines),
            llm_used=False,
            llm_unavailable=False,
        )

    def _handle_why(self, question: str, txn_id: str, entry: dict) -> QAAnswer:
        base_explanation = _compose_why_answer(txn_id, entry)
        retrieved = [{"transaction_id": txn_id, **entry["data"]}]
        explanation, llm_used, llm_unavailable = self._maybe_compose_with_llm(
            question, retrieved, base_explanation
        )
        return QAAnswer(
            intent=INTENT_WHY,
            question=question,
            found=True,
            supported=True,
            transaction_ids=[txn_id],
            retrieved_data=retrieved,
            explanation=explanation,
            llm_used=llm_used,
            llm_unavailable=llm_unavailable,
        )

    def _handle_evidence(self, question: str, txn_id: str, entry: dict) -> QAAnswer:
        base_explanation = _compose_evidence_answer(txn_id, entry)
        retrieved = [{"transaction_id": txn_id, **entry["data"]}]
        explanation, llm_used, llm_unavailable = self._maybe_compose_with_llm(
            question, retrieved, base_explanation
        )
        return QAAnswer(
            intent=INTENT_EVIDENCE,
            question=question,
            found=True,
            supported=True,
            transaction_ids=[txn_id],
            retrieved_data=retrieved,
            explanation=explanation,
            llm_used=llm_used,
            llm_unavailable=llm_unavailable,
        )

    def _handle_filter_status(self, question: str, status: str) -> QAAnswer:
        entries = self._index.filter_by_status(status)
        explanation = _compose_filter_answer(status, entries)
        txn_ids = [e["transaction_id"] for e in entries]
        return QAAnswer(
            intent=INTENT_FILTER_STATUS,
            question=question,
            found=True,
            supported=True,
            transaction_ids=txn_ids,
            retrieved_data=entries,
            explanation=explanation,
            llm_used=False,
            llm_unavailable=False,
        )

    def _handle_filter_rule(self, question: str, rule: str) -> QAAnswer:
        entries = self._index.filter_by_rule(rule)
        explanation = _compose_rule_filter_answer(rule, entries)
        txn_ids = [e["transaction_id"] for e in entries]
        return QAAnswer(
            intent=INTENT_FILTER_RULE,
            question=question,
            found=True,
            supported=True,
            transaction_ids=txn_ids,
            retrieved_data=entries,
            explanation=explanation,
            llm_used=False,
            llm_unavailable=False,
        )

    # -----------------------------------------------------------------------
    # Unsupported
    # -----------------------------------------------------------------------

    def _unsupported_answer(self, question: str) -> QAAnswer:
        return QAAnswer(
            intent=INTENT_UNSUPPORTED,
            question=question,
            found=False,
            supported=False,
            transaction_ids=[],
            retrieved_data=[],
            explanation=(
                "This question is outside the supported scope of the Settlement Q&A agent. "
                "Supported question types:\n"
                "  • 'What happened to PAY109?' — full lookup\n"
                "  • 'What is the status of PAY109?' — status only\n"
                "  • 'Why is PAY109 matched?' — explanation of the decision\n"
                "  • 'What evidence supports PAY109?' — evidence fields\n"
                "  • 'Which transactions need human review?' — status filter\n"
                "  • 'Show me unresolved transactions.' — status filter\n"
                "  • 'Which transactions were matched by the LLM-assisted "
                "split settlement rule?' — rule filter"
            ),
            llm_used=False,
            llm_unavailable=False,
        )

    # -----------------------------------------------------------------------
    # LLM prose composition (optional, non-blocking)
    # -----------------------------------------------------------------------

    def _maybe_compose_with_llm(
        self,
        question: str,
        retrieved: list[dict],
        base_explanation: str,
    ) -> tuple[str, bool, bool]:
        """
        Returns (explanation, llm_used, llm_unavailable).
        Falls back to base_explanation if Gemini is disabled or unavailable.
        """
        if not self._use_llm or self._llm is None:
            return base_explanation, False, False

        prose, used = _compose_with_gemini(question, retrieved, self._llm)
        if used and prose:
            return prose, True, False
        # Gemini was requested but failed — return template + flag
        return base_explanation, False, True


# ===========================================================================
# Convenience: build a SettlementQAAgent from raw pipeline output
# ===========================================================================


def build_qa_agent(
    tier1_results: list[Tier1Result],
    tier2_results: list[Tier2Result],
    tier3_results: list[Tier3Result],
    stage3_results: Optional[list[SplitResult]] = None,
    llm_client=None,
    use_llm_for_explanations: bool = False,
) -> SettlementQAAgent:
    """
    Convenience constructor: build the index and agent in one call.

    Typical usage:
        r1, _, matcher = run_tier1(data_dir="data", return_matcher=True)
        r2, _ = run_tier2(get_residue(r1), matcher)
        r3, _ = run_tier3(r2, matcher, llm_client=GeminiLLMClient())
        agent = build_qa_agent(r1, r2, r3, stage3_results=r4)
        answer = agent.ask("What happened to PAY109?")

    `stage3_results` (optional) is the Stage 3 split / multi-payment pass run on
    Tier 3 residue; when supplied its decisions are authoritative over Tier 3
    for the transactions it evaluated.
    """
    index = ReconciliationIndex(
        tier1_results, tier2_results, tier3_results, stage3_results
    )
    return SettlementQAAgent(
        index,
        llm_client=llm_client,
        use_llm_for_explanations=use_llm_for_explanations,
    )
