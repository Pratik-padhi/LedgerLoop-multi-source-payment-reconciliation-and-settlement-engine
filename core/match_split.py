"""
LedgerLoop — Stage 3: Generic Split / Multi-Payment Reconciliation
===================================================================

Supports one-to-many settlement relationships between a single gateway
transaction and multiple bank credit rows:

    SPLIT_SETTLEMENT_2_ROW  — gateway → exactly two bank credits
    SPLIT_SETTLEMENT_3_ROW  — gateway → exactly three bank credits
    MULTIPLE_PAYMENTS       — gateway → N bank credits (N <= MAX_COMBO_SIZE)
    PARTIAL_PAYMENT         — bank credits available sum to less than expected
                               settlement; explicitly distinguished from a full
                               reconciliation

GUIDING PRINCIPLE (unchanged from every prior tier)
------------------------------------------------------
"An unresolved transaction is better than an incorrect financial match."

STRICT ARCHITECTURAL BOUNDARY
-------------------------------
Stage 3 DOES:
    - consume the expected settlement amount from Stage 2 accounting
      (`core.accounting`) rather than re-implementing accounting formulas
    - operate only on records available after Tier 1 + Tier 2 consumption
    - enforce global bank-row uniqueness: a row consumed here is permanently
      unavailable to every other Stage 3 match in the same run
    - return explicit AMBIGUOUS / PARTIAL / UNRESOLVED results rather than
      guessing
    - call Gemini only when a plausible candidate set exists but evidence
      is genuinely ambiguous; Gemini recommends from a pre-vetted set only
    - independently re-validate every Gemini recommendation against raw
      records before accepting it

Stage 3 DOES NOT:
    - re-implement GST / TDS / MDR / fee arithmetic (delegates to accounting)
    - touch Tier 1 or Tier 2 MATCHED results
    - invent bank rows, amounts, or references
    - trust Gemini for arithmetic, candidate identity, or confidence
    - brute-force all combinations (bounded by MAX_COMBO_SIZE and
      CANDIDATE_FILTER_LIMIT)

COMBINATION SEARCH BOUNDS
--------------------------
To avoid combinatorial explosion the search is bounded at two levels:

1. CANDIDATE_FILTER_LIMIT (default 20): maximum bank rows admitted to the
   candidate pool for a single gateway transaction. Rows are filtered first
   by reference evidence (preferred) or amount proximity, then date proximity.
   A gateway with more than this many plausible candidates produces UNRESOLVED
   rather than exhaustive search.

2. MAX_COMBO_SIZE (default 4): maximum number of bank rows in one combination.
   Combinations of size 2, 3 … MAX_COMBO_SIZE are tried in ascending order;
   the first size that yields a valid, unambiguous combination is accepted.
   C(20, 4) = 4845 iterations worst case — fast in CPython.

ALLOCATION UNIQUENESS
----------------------
`SplitMatcher` carries a `_consumed` set that starts from Tier 1 + Tier 2
consumed rows. Every time a Stage 3 match is accepted the winning bank rows
are added to `_consumed` immediately, so a later gateway transaction cannot
claim them. When two gateways compete for the same combination the second one
finds the rows unavailable and yields AMBIGUOUS / UNRESOLVED appropriately.

PARTIAL PAYMENT SEMANTICS
--------------------------
When the best available bank total is less than the expected settlement the
result is SplitStatus.PARTIAL rather than a MATCH. The result carries:
    received       — sum of available matched bank credits
    outstanding    — expected_net − received
    evidence       — which rows contributed and why the total is short

A partial is never promoted to a full match by relaxing the tolerance.

ARITHMETIC TOLERANCE (SPLIT_TOLERANCE)
----------------------------------------
For a full split settlement the selected rows must sum to within ±SPLIT_TOLERANCE
of the accounting-computed expected_net. The value (₹5.00) is intentionally
wider than Tier 2's per-row ₹0.05 rounding tolerance because split settlements
may each carry small independent rounding differences. It matches the tolerance
already justified and in use in `core.match_llm.SPLIT_SETTLEMENT_TOLERANCE`.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from itertools import combinations
from typing import Optional

from core.normalize import CanonicalRecord
from core import accounting as accounting_model
from core.match_llm import (
    LLMClient, LLMUnavailableError,
    _minimal_gateway, _minimal_ledger, _minimal_bank,
    parse_llm_json,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration — explicit, documented, data-justified
# ---------------------------------------------------------------------------

# Maximum number of bank rows admitted to the candidate pool per gateway.
# Exceeding this yields UNRESOLVED rather than an unconstrained search.
CANDIDATE_FILTER_LIMIT: int = 20

# Maximum combination size (number of bank rows in one accepted combination).
# C(CANDIDATE_FILTER_LIMIT, MAX_COMBO_SIZE) = C(20,4) = 4845 iterations max.
MAX_COMBO_SIZE: int = 4

# Arithmetic tolerance for a split sum vs expected_net (positive Decimal INR).
# Wider than Tier 2's ₹0.05 per-row tolerance because each split credit may
# carry its own small independent rounding difference; a ₹5.00 gap on a
# ₹6400 transaction is 0.078%, well within reasonable settlement variance.
# Configurable per run; default retained for backwards compatibility.
SPLIT_TOLERANCE_DEFAULT = Decimal("5.00")

# A partial payment is recognised when available bank total is at least this
# fraction of expected_net. Below this threshold the match is UNRESOLVED
# (evidence too weak to call even a partial).
PARTIAL_PAYMENT_MIN_FRACTION = Decimal("0.10")


# ---------------------------------------------------------------------------
# Status / rule / reason taxonomy
# ---------------------------------------------------------------------------

class SplitStatus:
    MATCH = "MATCH"
    PARTIAL = "PARTIAL_PAYMENT"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    AI_RETRY_REQUIRED = "AI_RETRY_REQUIRED"


class SplitRule:
    SPLIT_2_ROW = "SPLIT_SETTLEMENT_2_ROW"
    SPLIT_3_ROW = "SPLIT_SETTLEMENT_3_ROW"
    MULTIPLE_PAYMENTS = "MULTIPLE_PAYMENTS"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"


class SplitReason:
    FULL_SUM_MATCH = "FULL_SUM_MATCH"
    PARTIAL_SUM_MATCH = "PARTIAL_SUM_MATCH"
    NO_CANDIDATES = "NO_CANDIDATES"
    CANDIDATE_LIMIT_EXCEEDED = "CANDIDATE_LIMIT_EXCEEDED"
    AMBIGUOUS_COMBINATIONS = "AMBIGUOUS_COMBINATIONS"
    INSUFFICIENT_PARTIAL = "INSUFFICIENT_PARTIAL"
    LLM_RECOMMENDATION_VALIDATED = "LLM_RECOMMENDATION_VALIDATED"
    LLM_RECOMMENDATION_REJECTED = "LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    ARITHMETIC_MISMATCH = "ARITHMETIC_MISMATCH"
    INVALID_CANDIDATE = "INVALID_CANDIDATE"
    AI_RETRY_REQUIRED = "AI_RETRY_REQUIRED"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SplitResult:
    """
    One structured Stage 3 decision for a single gateway transaction.

    bank_row_ids is the authoritative list of bank source_row_ids that together
    settle the gateway transaction. For one-to-one results it contains one id;
    for split / multiple-payment results it contains two or more. For non-MATCH
    results it reflects the best candidate set found (may be empty).
    """
    transaction_id: str
    status: str                         # SplitStatus.*
    rule: Optional[str]                 # SplitRule.* or None
    reason: Optional[str]               # SplitReason.* or None
    gateway_row_id: str
    bank_row_ids: list[str]             # empty → no bank rows selected
    ledger_row_id: Optional[str]
    expected_net: Optional[float]       # accounting-computed expected settlement
    received: Optional[float]           # sum of selected bank rows
    outstanding: Optional[float]        # expected_net − received  (None if full match)
    settlement: Optional[dict]          # SettlementBreakdown.to_dict() or None
    evidence: dict
    llm_consulted: bool = False
    llm_recommendation: Optional[dict] = None
    confidence: Optional[float] = None
    decision_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SplitSummary:
    total_evaluated: int
    match_count: int
    partial_count: int
    ambiguous_count: int
    unresolved_count: int
    ai_retry_count: int
    llm_calls_made: int
    llm_validated: int
    llm_rejected: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Tiny helpers (not duplicating normalize logic)
# ---------------------------------------------------------------------------

def _ref_value(record: CanonicalRecord, key: str) -> Optional[str]:
    ref = record.secondary_references.get(key)
    return ref.normalized if ref and ref.normalized else None


def _bank_amount(record: CanonicalRecord) -> Decimal:
    return Decimal(str(record.amount.normalized))


def _amounts_close(a: Decimal, b: Decimal, tol: Decimal = SPLIT_TOLERANCE_DEFAULT) -> bool:
    return abs(a - b) <= tol


def _rule_for_size(n: int) -> str:
    if n == 2:
        return SplitRule.SPLIT_2_ROW
    if n == 3:
        return SplitRule.SPLIT_3_ROW
    return SplitRule.MULTIPLE_PAYMENTS


# ---------------------------------------------------------------------------
# Candidate filtering
# ---------------------------------------------------------------------------

def _build_candidate_pool(
    gw: CanonicalRecord,
    ledger: Optional[CanonicalRecord],
    all_bank: list[CanonicalRecord],
    consumed: set[str],
    expected_net: Decimal,
    limit: int = CANDIDATE_FILTER_LIMIT,
) -> tuple[list[CanonicalRecord], str]:
    """
    Filter the full bank record list down to a bounded candidate pool.

    Strategy (ordered preference):
      1. Reference evidence: bank_reference contains gateway_reference digits,
         or bank description contains gateway customer_reference /
         ledger invoice_reference.
      2. Amount proximity: bank amount is within SPLIT_TOLERANCE of
         expected_net (as a single row) or less than expected_net (could be
         one part of a split).
      3. Date proximity: settlement date within 7 days of gateway date.

    Returns (candidates, reason_if_exceeded).
    reason_if_exceeded is SplitReason.CANDIDATE_LIMIT_EXCEEDED when the
    unfiltered pool exceeds `limit`; otherwise empty string.
    """
    available = [b for b in all_bank if b.source_row_id not in consumed]

    gw_ref = _ref_value(gw, "gateway_reference") or ""
    gw_customer_ref = _ref_value(gw, "customer_reference") or ""
    ledger_invoice_ref = _ref_value(ledger, "invoice_reference") if ledger else ""

    # Digit suffix of gateway reference for partial reference matching
    gw_digits = ""
    if gw_ref.startswith("GW") and gw_ref[2:].isdigit():
        gw_digits = gw_ref[2:]

    def _has_reference_evidence(b: CanonicalRecord) -> bool:
        bank_ref = (_ref_value(b, "bank_reference") or "").upper()
        desc = (_ref_value(b, "description") or "").upper()
        if gw_ref and gw_ref.upper() in bank_ref:
            return True
        if gw_digits and gw_digits in bank_ref:
            return True
        if gw_customer_ref and gw_customer_ref.upper() in desc:
            return True
        if ledger_invoice_ref and ledger_invoice_ref.upper() in desc:
            return True
        return False

    def _is_amount_plausible(b: CanonicalRecord) -> bool:
        amt = _bank_amount(b)
        # Row could be one part of a split: it must be < expected_net + tolerance
        # and at least 1% of expected_net (avoids tiny noise rows)
        if expected_net <= 0:
            return False
        return amt > 0 and amt <= (expected_net + SPLIT_TOLERANCE_DEFAULT) and amt >= (expected_net * Decimal("0.01"))

    # Prefer reference-evidenced rows
    ref_pool = [b for b in available if _has_reference_evidence(b)]
    amt_pool = [b for b in available if not _has_reference_evidence(b) and _is_amount_plausible(b)]

    combined = ref_pool + amt_pool

    if len(combined) > limit:
        return combined[:limit], SplitReason.CANDIDATE_LIMIT_EXCEEDED

    return combined, ""


# ---------------------------------------------------------------------------
# Core SplitMatcher
# ---------------------------------------------------------------------------

class SplitMatcher:
    """
    Stateful Stage 3 one-to-many matcher.

    Enforces global bank-row uniqueness: once a bank row is accepted into a
    Stage 3 match it is added to `_consumed` and permanently unavailable for
    subsequent gateway transactions in the same run.

    Designed to be called once per pipeline run via `run_stage3()`.
    """

    def __init__(
        self,
        gateway_records: list[CanonicalRecord],
        bank_records: list[CanonicalRecord],
        ledger_records: list[CanonicalRecord],
        already_consumed: set[str],
        llm_client: Optional[LLMClient] = None,
        candidate_filter_limit: int = CANDIDATE_FILTER_LIMIT,
        max_combo_size: int = MAX_COMBO_SIZE,
        split_tolerance: Decimal = SPLIT_TOLERANCE_DEFAULT,
    ):
        self.gw_by_id = {r.source_row_id: r for r in gateway_records}
        self.bank_by_id = {r.source_row_id: r for r in bank_records}
        self.ledger_by_id = {r.source_row_id: r for r in ledger_records}
        self.all_bank = list(bank_records)

        self._consumed: set[str] = set(already_consumed)
        self.llm_client = llm_client
        self.candidate_filter_limit = candidate_filter_limit
        self.max_combo_size = max_combo_size
        self.split_tolerance = split_tolerance

        self.llm_calls_made = 0
        self.llm_validated = 0
        self.llm_rejected = 0

    # -- availability -------------------------------------------------------

    def _is_available(self, row_id: str) -> bool:
        return row_id not in self._consumed

    def _consume_all(self, row_ids: list[str]) -> None:
        for rid in row_ids:
            self._consumed.add(rid)

    # -- expected settlement ------------------------------------------------

    def _expected_net(
        self, gw: CanonicalRecord, ledger: Optional[CanonicalRecord]
    ) -> tuple[Decimal, Optional[dict]]:
        """
        Compute expected net settlement using Stage 2 accounting.
        Returns (expected_net_decimal, settlement_breakdown_dict_or_None).
        Delegates entirely to core.accounting — never re-implements formulas.
        """
        gross = gw.amount.normalized
        if gross is None:
            return Decimal("0"), None

        # A negative gateway gross is a refund transaction. Stage 3 is the
        # split / multi-payment reconciliation pass for *payment* transactions;
        # refunds are Tier 3's REFUND_LINKED_NET_AMOUNT domain and are not
        # settled by a candidate pool of positive bank credits. Return the
        # (negative) gross unchanged so run_stage3's `expected_net <= 0` branch
        # classifies it UNRESOLVED / NO_CANDIDATES instead of feeding a
        # negative amount into the accounting layer (which would raise).
        gross_dec = Decimal(str(gross))
        if gross_dec < 0:
            return gross_dec, None

        if ledger is None:
            # No ledger context: expected = gross (no adjustments known)
            return gross_dec, None

        breakdown = accounting_model.build_settlement_from_ledger(
            gross, ledger,
            actual_bank=None,
            source_rows={
                "gateway": gw.source_row_id,
                "ledger": ledger.source_row_id,
            },
        )
        exp = Decimal(str(breakdown.expected_net_amount)) if breakdown.expected_net_amount is not None else gross_dec
        return exp, breakdown.to_dict()

    # -- combination search -------------------------------------------------

    def _find_valid_combinations(
        self,
        candidates: list[CanonicalRecord],
        expected_net: Decimal,
    ) -> list[tuple[CanonicalRecord, ...]]:
        """
        Find all combinations (size 2..max_combo_size) of available candidate
        rows whose bank amount sum is within the configured split tolerance of expected_net.

        Only considers rows that are still available at call time.
        Returns every valid combination found — caller detects ambiguity.
        """
        available = [c for c in candidates if self._is_available(c.source_row_id)]
        valid: list[tuple[CanonicalRecord, ...]] = []

        for size in range(2, min(self.max_combo_size, len(available)) + 1):
            for combo in combinations(available, size):
                total = sum(_bank_amount(b) for b in combo)
                if _amounts_close(total, expected_net, self.split_tolerance):
                    valid.append(combo)

        return valid

    def _find_partial_combination(
        self,
        candidates: list[CanonicalRecord],
        expected_net: Decimal,
    ) -> Optional[list[CanonicalRecord]]:
        """
        Find the combination of available rows whose sum is the closest to
        (but strictly less than) expected_net, for partial-payment detection.
        Returns the best single combination or None if no plausible partial
        exists.

        Only returns a partial when:
          - the sum is < expected_net (not a rounding overshoot)
          - the sum is >= PARTIAL_PAYMENT_MIN_FRACTION * expected_net
          - there is exactly one "best" combination at the closest distance
            (ties → None, ambiguous partial)
        """
        available = [c for c in candidates if self._is_available(c.source_row_id)]
        if not available or expected_net <= 0:
            return None

        best_combo: Optional[list[CanonicalRecord]] = None
        best_diff = expected_net  # start at max
        ambiguous = False

        min_received = expected_net * PARTIAL_PAYMENT_MIN_FRACTION

        for size in range(1, min(self.max_combo_size, len(available)) + 1):
            for combo in combinations(available, size):
                total = sum(_bank_amount(b) for b in combo)
                if total >= expected_net:
                    continue  # overshoot → not a partial
                if total < min_received:
                    continue  # too small to be meaningful
                diff = expected_net - total
                if diff < best_diff:
                    best_diff = diff
                    best_combo = list(combo)
                    ambiguous = False
                elif diff == best_diff:
                    ambiguous = True

        if ambiguous:
            return None
        return best_combo

    # -- LLM adjudication for genuinely ambiguous splits --------------------

    def _llm_adjudicate_ambiguous(
        self,
        txn_id: str,
        gw: CanonicalRecord,
        ledger: Optional[CanonicalRecord],
        candidates: list[CanonicalRecord],
        valid_combos: list[tuple[CanonicalRecord, ...]],
        expected_net: Decimal,
    ) -> tuple[Optional[list[str]], Optional[dict], str]:
        """
        Called when >1 valid combination exists and LLM adjudication is
        warranted. Returns (validated_bank_ids, raw_recommendation, reason).

        Python independently validates every LLM recommendation:
          - all ids must be in the pre-vetted candidate set
          - all ids must still be available
          - no duplicates
          - arithmetic must hold within configured split_tolerance
        """
        if self.llm_client is None:
            return None, None, SplitReason.LLM_UNAVAILABLE

        available_ids = [c.source_row_id for c in candidates if self._is_available(c.source_row_id)]

        prompt_payload = {
            "gateway_payment": _minimal_gateway(gw),
            "ledger_entry": _minimal_ledger(ledger) if ledger else None,
            "candidate_bank_credits": [
                _minimal_bank(self.bank_by_id[bid]) for bid in available_ids
            ],
            "valid_combinations": [
                [b.source_row_id for b in combo] for combo in valid_combos
            ],
            "question": (
                "Multiple combinations of these bank credits could settle the "
                "gateway payment. Which combination is the correct one? Name "
                "exactly the source_row_ids that belong together."
            ),
        }
        system = (
            "You are assisting a payment-reconciliation system. You only "
            "see the minimal record excerpts provided. Respond with ONLY a "
            "JSON object: "
            '{"decision": "<MATCH|HUMAN_REVIEW>", '
            '"bank_row_ids": ["<source_row_id>", ...], '
            '"confidence": <0.0-1.0>, '
            '"rationale": "<explanation>", '
            '"evidence": {}, "adjustment": {}}. '
            "bank_row_ids MUST be source_row_ids from the candidate list. "
            "Do not invent IDs. If evidence is symmetric or missing, use "
            "HUMAN_REVIEW. Do NOT wrap JSON in markdown fences."
        )

        self.llm_calls_made += 1
        try:
            raw = self.llm_client.complete(system, json.dumps(prompt_payload))
        except LLMUnavailableError:
            return None, None, SplitReason.LLM_UNAVAILABLE

        rec = parse_llm_json(raw)
        if rec is None:
            self.llm_rejected += 1
            return None, {"decision": "HUMAN_REVIEW", "rationale": "unparseable response"}, \
                SplitReason.LLM_RECOMMENDATION_REJECTED

        validated, rejection_reason = self._validate_llm_recommendation(rec, available_ids, expected_net)
        if validated is not None:
            self.llm_validated += 1
            return validated, rec, SplitReason.LLM_RECOMMENDATION_VALIDATED

        self.llm_rejected += 1
        return None, rec, rejection_reason or SplitReason.LLM_RECOMMENDATION_REJECTED

    def _validate_llm_recommendation(
        self,
        rec: dict,
        available_ids: list[str],
        expected_net: Decimal,
    ) -> tuple[Optional[list[str]], Optional[str]]:
        """
        Independently re-validate a Gemini recommendation before accepting.
        Never trusts Gemini's stated arithmetic, confidence, or candidate identity.
        """
        if rec.get("decision") != "MATCH":
            return None, "NON_MATCH_DECISION"

        confidence = rec.get("confidence")
        if confidence is None:
            return None, SplitReason.LLM_RECOMMENDATION_REJECTED
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None, SplitReason.LLM_RECOMMENDATION_REJECTED
        if not (0.0 <= confidence <= 1.0):
            return None, SplitReason.LLM_RECOMMENDATION_REJECTED

        for fn in ("evidence", "adjustment"):
            if not isinstance(rec.get(fn, {}), dict):
                return None, SplitReason.LLM_RECOMMENDATION_REJECTED

        ids = rec.get("bank_row_ids")
        if not isinstance(ids, list) or len(ids) < 2:
            return None, "INSUFFICIENT_BANK_ROWS"
        if any(not isinstance(i, str) for i in ids):
            return None, "INVALID_BANK_ROW_ID_TYPE"
        if any(i not in available_ids for i in ids):
            return None, "CANDIDATE_NOT_IN_PREVETTED_SET"
        if len(set(ids)) != len(ids):
            return None, "DUPLICATE_BANK_ROW_ID"
        for i in ids:
            if not self._is_available(i):
                return None, "CANDIDATE_NO_LONGER_AVAILABLE"

        # Re-compute arithmetic independently (never trust LLM's stated sum)
        total = sum(_bank_amount(self.bank_by_id[i]) for i in ids)
        if not _amounts_close(total, expected_net, self.split_tolerance):
            return None, SplitReason.ARITHMETIC_MISMATCH

        return ids, None

    # -- top-level per-transaction resolution --------------------------------

    def resolve(
        self,
        txn_id: str,
        gw_row_id: str,
        ledger_row_id: Optional[str],
    ) -> SplitResult:
        """
        Attempt Stage 3 split / multi-payment resolution for one gateway
        transaction whose Tier 1/2/3 one-to-one matching did not succeed.

        Args:
            txn_id:       logical transaction id (gateway payment_id)
            gw_row_id:    gateway source_row_id
            ledger_row_id: ledger source_row_id or None
        """
        gw = self.gw_by_id[gw_row_id]
        ledger = self.ledger_by_id.get(ledger_row_id) if ledger_row_id else None

        # Step 1: compute expected settlement via Stage 2 accounting
        expected_net, settlement_dict = self._expected_net(gw, ledger)

        if expected_net <= 0:
            return self._result(
                txn_id, SplitStatus.UNRESOLVED, None, SplitReason.NO_CANDIDATES,
                gw_row_id, [], ledger_row_id, expected_net, settlement_dict,
                evidence={"reason": "non-positive expected_net"},
            )

        # Step 2: build candidate pool
        candidates, filter_reason = _build_candidate_pool(
            gw, ledger, self.all_bank, self._consumed, expected_net,
            self.candidate_filter_limit,
        )

        if not candidates:
            return self._result(
                txn_id, SplitStatus.UNRESOLVED, None, SplitReason.NO_CANDIDATES,
                gw_row_id, [], ledger_row_id, expected_net, settlement_dict,
                evidence={"expected_net": float(expected_net)},
            )

        if filter_reason == SplitReason.CANDIDATE_LIMIT_EXCEEDED:
            return self._result(
                txn_id, SplitStatus.UNRESOLVED, None, SplitReason.CANDIDATE_LIMIT_EXCEEDED,
                gw_row_id, [], ledger_row_id, expected_net, settlement_dict,
                evidence={
                    "expected_net": float(expected_net),
                    "candidate_count_before_limit": len(candidates),
                    "configured_limit": self.candidate_filter_limit,
                },
            )

        # Step 3: find valid combinations
        valid_combos = self._find_valid_combinations(candidates, expected_net)

        # Step 4: zero valid combinations → check for partial payment
        if not valid_combos:
            return self._try_partial(
                txn_id, gw_row_id, ledger_row_id, gw, ledger, candidates,
                expected_net, settlement_dict,
            )

        # Step 5: exactly one combination → deterministic match (no LLM needed)
        if len(valid_combos) == 1:
            winning = list(valid_combos[0])
            winning_ids = [b.source_row_id for b in winning]
            total = sum(_bank_amount(b) for b in winning)

            # Update settlement breakdown with actual bank total
            final_settlement = self._settlement_with_bank(gw, ledger, float(total))
            self._consume_all(winning_ids)

            return self._result(
                txn_id, SplitStatus.MATCH, _rule_for_size(len(winning)),
                SplitReason.FULL_SUM_MATCH,
                gw_row_id, winning_ids, ledger_row_id, expected_net, final_settlement,
                received=total, outstanding=None,
                evidence={
                    "expected_net": float(expected_net),
                    "bank_credit_total": float(total),
                    "bank_row_ids": winning_ids,
                    "combination_size": len(winning),
                    "tolerance_used": float(self.split_tolerance),
                },
                llm_consulted=False,
            )

        # Step 6: multiple valid combinations → attempt LLM adjudication
        llm_ids, llm_rec, llm_reason = self._llm_adjudicate_ambiguous(
            txn_id, gw, ledger, candidates, valid_combos, expected_net
        )
        llm_was_called = self.llm_calls_made > 0  # conservative — tracks total, not per-txn

        if llm_ids:
            total = sum(_bank_amount(self.bank_by_id[bid]) for bid in llm_ids)
            final_settlement = self._settlement_with_bank(gw, ledger, float(total))
            self._consume_all(llm_ids)

            return self._result(
                txn_id, SplitStatus.MATCH, _rule_for_size(len(llm_ids)),
                SplitReason.LLM_RECOMMENDATION_VALIDATED,
                gw_row_id, llm_ids, ledger_row_id, expected_net, final_settlement,
                received=total, outstanding=None,
                evidence={
                    "expected_net": float(expected_net),
                    "bank_credit_total": float(total),
                    "bank_row_ids": llm_ids,
                    "combination_size": len(llm_ids),
                    "ambiguous_combo_count": len(valid_combos),
                    "llm_evidence": llm_rec.get("evidence", {}) if llm_rec else {},
                },
                llm_consulted=True,
                llm_recommendation=llm_rec,
                confidence=llm_rec.get("confidence") if llm_rec else None,
            )

        # LLM unavailable or rejected → AI_RETRY_REQUIRED or AMBIGUOUS
        if llm_reason == SplitReason.LLM_UNAVAILABLE:
            status = SplitStatus.AI_RETRY_REQUIRED
            reason = SplitReason.AI_RETRY_REQUIRED
        else:
            status = SplitStatus.AMBIGUOUS
            reason = SplitReason.AMBIGUOUS_COMBINATIONS

        all_combo_ids = [[b.source_row_id for b in c] for c in valid_combos]
        return self._result(
            txn_id, status, None, reason,
            gw_row_id, [], ledger_row_id, expected_net, settlement_dict,
            evidence={
                "expected_net": float(expected_net),
                "valid_combination_count": len(valid_combos),
                "valid_combinations": all_combo_ids,
                "llm_recommendation": llm_rec,
            },
            llm_consulted=llm_was_called,
            llm_recommendation=llm_rec,
        )

    # -- partial-payment sub-resolver ----------------------------------------

    def _try_partial(
        self,
        txn_id: str,
        gw_row_id: str,
        ledger_row_id: Optional[str],
        gw: CanonicalRecord,
        ledger: Optional[CanonicalRecord],
        candidates: list[CanonicalRecord],
        expected_net: Decimal,
        settlement_dict: Optional[dict],
    ) -> SplitResult:
        partial = self._find_partial_combination(candidates, expected_net)
        if partial is None:
            return self._result(
                txn_id, SplitStatus.UNRESOLVED, None, SplitReason.INSUFFICIENT_PARTIAL,
                gw_row_id, [], ledger_row_id, expected_net, settlement_dict,
                evidence={
                    "expected_net": float(expected_net),
                    "candidate_count": len(candidates),
                    "reason": "no plausible partial combination found",
                },
            )

        partial_ids = [b.source_row_id for b in partial]
        received = sum(_bank_amount(b) for b in partial)
        outstanding = expected_net - received

        if received < expected_net * PARTIAL_PAYMENT_MIN_FRACTION:
            return self._result(
                txn_id, SplitStatus.UNRESOLVED, None, SplitReason.INSUFFICIENT_PARTIAL,
                gw_row_id, [], ledger_row_id, expected_net, settlement_dict,
                evidence={
                    "expected_net": float(expected_net),
                    "best_partial_total": float(received),
                    "reason": "partial total below minimum fraction threshold",
                },
            )

        # Do NOT consume partial rows — a partial match does not lock them;
        # a human must confirm before the rows are allocated. This prevents
        # a speculative partial from blocking a later correct match.
        final_settlement = self._settlement_with_bank(gw, ledger, float(received))
        return self._result(
            txn_id, SplitStatus.PARTIAL, SplitRule.PARTIAL_PAYMENT,
            SplitReason.PARTIAL_SUM_MATCH,
            gw_row_id, partial_ids, ledger_row_id, expected_net, final_settlement,
            received=received,
            outstanding=outstanding,
            evidence={
                "expected_net": float(expected_net),
                "received": float(received),
                "outstanding": float(outstanding),
                "bank_row_ids": partial_ids,
                "bank_row_amounts": [float(_bank_amount(b)) for b in partial],
                "candidate_count": len(candidates),
            },
        )

    # -- accounting helper ---------------------------------------------------

    def _settlement_with_bank(
        self,
        gw: CanonicalRecord,
        ledger: Optional[CanonicalRecord],
        actual_bank: float,
    ) -> Optional[dict]:
        gross = gw.amount.normalized
        if gross is None:
            return None
        if ledger is None:
            breakdown = accounting_model.compute_settlement(
                gross, actual_bank=actual_bank,
                source_rows={"gateway": gw.source_row_id},
            )
        else:
            breakdown = accounting_model.build_settlement_from_ledger(
                gross, ledger,
                actual_bank=actual_bank,
                source_rows={"gateway": gw.source_row_id, "ledger": ledger.source_row_id},
            )
        return breakdown.to_dict()

    # -- result builder ------------------------------------------------------

    @staticmethod
    def _result(
        txn_id: str,
        status: str,
        rule: Optional[str],
        reason: Optional[str],
        gw_row_id: str,
        bank_row_ids: list[str],
        ledger_row_id: Optional[str],
        expected_net: Decimal,
        settlement: Optional[dict],
        received: Optional[Decimal] = None,
        outstanding: Optional[Decimal] = None,
        evidence: Optional[dict] = None,
        llm_consulted: bool = False,
        llm_recommendation: Optional[dict] = None,
        confidence: Optional[float] = None,
    ) -> SplitResult:
        return SplitResult(
            transaction_id=txn_id,
            status=status,
            rule=rule,
            reason=reason,
            gateway_row_id=gw_row_id,
            bank_row_ids=list(bank_row_ids),
            ledger_row_id=ledger_row_id,
            expected_net=float(expected_net) if expected_net else None,
            received=float(received) if received is not None else None,
            outstanding=float(outstanding) if outstanding is not None else None,
            settlement=settlement,
            evidence=evidence or {},
            llm_consulted=llm_consulted,
            llm_recommendation=llm_recommendation,
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_stage3(
    gateway_records: list[CanonicalRecord],
    bank_records: list[CanonicalRecord],
    ledger_records: list[CanonicalRecord],
    already_consumed: set[str],
    pending_txns: list[dict],
    llm_client: Optional[LLMClient] = None,
    candidate_filter_limit: int = CANDIDATE_FILTER_LIMIT,
    max_combo_size: int = MAX_COMBO_SIZE,
    split_tolerance: Decimal = SPLIT_TOLERANCE_DEFAULT,
) -> tuple[list[SplitResult], SplitSummary]:
    """
    Run Stage 3 generic split / multi-payment reconciliation.

    Args:
        gateway_records:        all normalized gateway CanonicalRecords
        bank_records:           all normalized bank CanonicalRecords
        ledger_records:         all normalized ledger CanonicalRecords
        already_consumed:       set of bank source_row_ids already claimed by
                                Tier 1 / Tier 2 / Tier 3 one-to-one matching
        pending_txns:           list of dicts — each must have:
                                  "transaction_id"   (str)
                                  "gateway_row_id"   (str)
                                  "ledger_row_id"    (str | None)
        llm_client:             optional LLMClient for ambiguous adjudication
        candidate_filter_limit: override CANDIDATE_FILTER_LIMIT per run
        max_combo_size:         override MAX_COMBO_SIZE per run
        split_tolerance:        arithmetic tolerance for split sum vs expected_net

    Returns:
        (results, summary) — one SplitResult per pending_txns entry.
    """
    # Two-pass architecture to handle competing gateways fairly:
    # Pass 1: compute all valid combinations for all transactions (no consumption)
    # Pass 2: detect conflicts, resolve, then consume rows

    matcher = SplitMatcher(
        gateway_records=gateway_records,
        bank_records=bank_records,
        ledger_records=ledger_records,
        already_consumed=already_consumed,
        llm_client=llm_client,
        candidate_filter_limit=candidate_filter_limit,
        max_combo_size=max_combo_size,
        split_tolerance=split_tolerance,
    )

    # Pass 1: find all valid combinations for all transactions
    txn_combinations: dict[str, dict] = {}
    for txn in pending_txns:
        txn_id = txn["transaction_id"]
        gw_row_id = txn["gateway_row_id"]
        ledger_row_id = txn.get("ledger_row_id")

        gw = matcher.gw_by_id[gw_row_id]
        ledger = matcher.ledger_by_id.get(ledger_row_id) if ledger_row_id else None
        expected_net, settlement_dict = matcher._expected_net(gw, ledger)

        if expected_net <= 0:
            txn_combinations[txn_id] = {
                "txn": txn,
                "gw": gw,
                "ledger": ledger,
                "expected_net": expected_net,
                "settlement_dict": settlement_dict,
                "candidates": [],
                "valid_combos": [],
                "partial": None,
                "filter_reason": "non-positive expected_net",
                "status": SplitStatus.UNRESOLVED,
                "reason": SplitReason.NO_CANDIDATES,
            }
            continue

        candidates, filter_reason = _build_candidate_pool(
            gw, ledger, matcher.all_bank, matcher._consumed, expected_net,
            matcher.candidate_filter_limit,
        )

        if filter_reason == SplitReason.CANDIDATE_LIMIT_EXCEEDED:
            txn_combinations[txn_id] = {
                "txn": txn,
                "gw": gw,
                "ledger": ledger,
                "expected_net": expected_net,
                "settlement_dict": settlement_dict,
                "candidates": candidates,
                "valid_combos": [],
                "partial": None,
                "filter_reason": filter_reason,
                "status": SplitStatus.UNRESOLVED,
                "reason": SplitReason.CANDIDATE_LIMIT_EXCEEDED,
            }
            continue

        if not candidates:
            txn_combinations[txn_id] = {
                "txn": txn,
                "gw": gw,
                "ledger": ledger,
                "expected_net": expected_net,
                "settlement_dict": settlement_dict,
                "candidates": [],
                "valid_combos": [],
                "partial": None,
                "filter_reason": "no candidates",
                "status": SplitStatus.UNRESOLVED,
                "reason": SplitReason.NO_CANDIDATES,
            }
            continue

        valid_combos = matcher._find_valid_combinations(candidates, expected_net)
        partial = None
        if not valid_combos:
            partial = matcher._find_partial_combination(candidates, expected_net)

        txn_combinations[txn_id] = {
            "txn": txn,
            "gw": gw,
            "ledger": ledger,
            "expected_net": expected_net,
            "settlement_dict": settlement_dict,
            "candidates": candidates,
            "valid_combos": valid_combos,
            "partial": partial,
            "filter_reason": "",
            "status": None,
            "reason": None,
        }

    # Pass 2: detect conflicts among transactions with single valid combo
    combo_to_txns: dict[frozenset, list[str]] = defaultdict(list)
    for txn_id, data in txn_combinations.items():
        if len(data["valid_combos"]) == 1:
            combo_ids = frozenset(b.source_row_id for b in data["valid_combos"][0])
            combo_to_txns[combo_ids].append(txn_id)

    conflicted_combos: set[frozenset] = set()
    for combo_ids, txn_ids in combo_to_txns.items():
        if len(txn_ids) > 1:
            conflicted_combos.add(combo_ids)

    # Mark conflicted transactions as AMBIGUOUS
    for txn_id, data in txn_combinations.items():
        if data["status"] is not None:
            continue
        if len(data["valid_combos"]) == 1:
            combo_ids = frozenset(b.source_row_id for b in data["valid_combos"][0])
            if combo_ids in conflicted_combos:
                data["status"] = SplitStatus.AMBIGUOUS
                data["reason"] = SplitReason.AMBIGUOUS_COMBINATIONS

    # Pass 3: resolve each transaction in order
    results: list[SplitResult] = []
    for txn in pending_txns:
        txn_id = txn["transaction_id"]
        data = txn_combinations[txn_id]

        if data["status"] is not None:
            # Already determined (UNRESOLVED from pass 1, or AMBIGUOUS from conflict)
            r = matcher._result(
                txn_id, data["status"], None, data["reason"],
                data["txn"]["gateway_row_id"], [], data["txn"].get("ledger_row_id"),
                data["expected_net"], data["settlement_dict"],
                evidence={
                    "expected_net": float(data["expected_net"]),
                    "valid_combination_count": len(data["valid_combos"]),
                    "valid_combinations": [[b.source_row_id for b in c] for c in data["valid_combos"]],
                },
            )
            results.append(r)
            continue

        if not data["valid_combos"]:
            # No valid combos → try partial
            if data["partial"] is not None:
                r = matcher._try_partial(
                    txn_id, data["txn"]["gateway_row_id"], data["txn"].get("ledger_row_id"),
                    data["gw"], data["ledger"], data["candidates"],
                    data["expected_net"], data["settlement_dict"],
                )
            else:
                r = matcher._result(
                    txn_id, SplitStatus.UNRESOLVED, None, SplitReason.INSUFFICIENT_PARTIAL,
                    data["txn"]["gateway_row_id"], [], data["txn"].get("ledger_row_id"),
                    data["expected_net"], data["settlement_dict"],
                    evidence={
                        "expected_net": float(data["expected_net"]),
                        "candidate_count": len(data["candidates"]),
                        "reason": "no plausible partial combination found",
                    },
                )
            results.append(r)
            continue

        # Exactly one valid combo, not conflicted → deterministic MATCH
        if len(data["valid_combos"]) == 1:
            winning = list(data["valid_combos"][0])
            winning_ids = [b.source_row_id for b in winning]
            total = sum(_bank_amount(b) for b in winning)
            final_settlement = matcher._settlement_with_bank(data["gw"], data["ledger"], float(total))
            matcher._consume_all(winning_ids)

            r = matcher._result(
                txn_id, SplitStatus.MATCH, _rule_for_size(len(winning)),
                SplitReason.FULL_SUM_MATCH,
                data["txn"]["gateway_row_id"], winning_ids, data["txn"].get("ledger_row_id"),
                data["expected_net"], final_settlement,
                received=total, outstanding=None,
                evidence={
                    "expected_net": float(data["expected_net"]),
                    "bank_credit_total": float(total),
                    "bank_row_ids": winning_ids,
                    "combination_size": len(winning),
                    "tolerance_used": float(matcher.split_tolerance),
                },
                llm_consulted=False,
            )
            results.append(r)
            continue

        # Multiple valid combos → LLM adjudication
        llm_ids, llm_rec, llm_reason = matcher._llm_adjudicate_ambiguous(
            txn_id, data["gw"], data["ledger"], data["candidates"],
            data["valid_combos"], data["expected_net"]
        )
        llm_was_called = matcher.llm_calls_made > 0

        if llm_ids:
            total = sum(_bank_amount(matcher.bank_by_id[bid]) for bid in llm_ids)
            final_settlement = matcher._settlement_with_bank(data["gw"], data["ledger"], float(total))
            matcher._consume_all(llm_ids)

            r = matcher._result(
                txn_id, SplitStatus.MATCH, _rule_for_size(len(llm_ids)),
                SplitReason.LLM_RECOMMENDATION_VALIDATED,
                data["txn"]["gateway_row_id"], llm_ids, data["txn"].get("ledger_row_id"),
                data["expected_net"], final_settlement,
                received=total, outstanding=None,
                evidence={
                    "expected_net": float(data["expected_net"]),
                    "bank_credit_total": float(total),
                    "bank_row_ids": llm_ids,
                    "combination_size": len(llm_ids),
                    "ambiguous_combo_count": len(data["valid_combos"]),
                    "llm_evidence": llm_rec.get("evidence", {}) if llm_rec else {},
                },
                llm_consulted=True,
                llm_recommendation=llm_rec,
                confidence=llm_rec.get("confidence") if llm_rec else None,
            )
            results.append(r)
            continue

        # LLM unavailable or rejected
        if llm_reason == SplitReason.LLM_UNAVAILABLE:
            status = SplitStatus.AI_RETRY_REQUIRED
            reason = SplitReason.AI_RETRY_REQUIRED
        else:
            status = SplitStatus.AMBIGUOUS
            reason = SplitReason.AMBIGUOUS_COMBINATIONS

        all_combo_ids = [[b.source_row_id for b in c] for c in data["valid_combos"]]
        r = matcher._result(
            txn_id, status, None, reason,
            data["txn"]["gateway_row_id"], [], data["txn"].get("ledger_row_id"),
            data["expected_net"], data["settlement_dict"],
            evidence={
                "expected_net": float(data["expected_net"]),
                "valid_combination_count": len(data["valid_combos"]),
                "valid_combinations": all_combo_ids,
                "llm_recommendation": llm_rec,
            },
            llm_consulted=llm_was_called,
            llm_recommendation=llm_rec,
        )
        results.append(r)

    match_count = sum(1 for r in results if r.status == SplitStatus.MATCH)
    partial_count = sum(1 for r in results if r.status == SplitStatus.PARTIAL)
    ambiguous_count = sum(1 for r in results if r.status == SplitStatus.AMBIGUOUS)
    ai_retry = sum(1 for r in results if r.status == SplitStatus.AI_RETRY_REQUIRED)
    unresolved_count = sum(1 for r in results if r.status == SplitStatus.UNRESOLVED)

    summary = SplitSummary(
        total_evaluated=len(results),
        match_count=match_count,
        partial_count=partial_count,
        ambiguous_count=ambiguous_count,
        unresolved_count=unresolved_count,
        ai_retry_count=ai_retry,
        llm_calls_made=matcher.llm_calls_made,
        llm_validated=matcher.llm_validated,
        llm_rejected=matcher.llm_rejected,
    )
    return results, summary


def retry_stage3_transaction(
    txn_id: str,
    pending_txn: dict,
    gateway_records: list[CanonicalRecord],
    bank_records: list[CanonicalRecord],
    ledger_records: list[CanonicalRecord],
    already_consumed: set[str],
    stage3_consumed: set[str],
    llm_client: Optional[LLMClient],
    split_tolerance: Decimal = SPLIT_TOLERANCE_DEFAULT,
) -> SplitResult:
    """Re-adjudicate ONE Stage 3 AI_RETRY_REQUIRED transaction with a client.

    This deliberately does not rerun normalization, Tier 1/2/3, or the rest of
    Stage 3. It rebuilds a fresh SplitMatcher seeded with the *current*
    consumed bank-row state (Tier 1/2/3 one-to-one claims plus bank rows already
    claimed by other Stage 3 MATCH results) and a supplied LLM client, then
    resolves exactly this transaction via the normal deterministic-then-LLM
    path (`SplitMatcher.resolve`). The result is a brand-new SplitResult and
    nothing is mutated on any shared matcher.

    The retried transaction must be one whose prior disposition was
    AI_RETRY_REQUIRED (LLM was unavailable); all arithmetic, candidate
    availability and uniqueness validation remain Python-authoritative.
    """
    matcher = SplitMatcher(
        gateway_records=gateway_records,
        bank_records=bank_records,
        ledger_records=ledger_records,
        already_consumed=already_consumed | stage3_consumed,
        llm_client=llm_client,
        split_tolerance=split_tolerance,
    )
    return matcher.resolve(
        txn_id,
        pending_txn["gateway_row_id"],
        pending_txn.get("ledger_row_id"),
    )
