"""
LedgerLoop — Phase 4: Tier 2 Deterministic Fuzzy / Tolerance Matching
=========================================================================

Consumes the Tier 1 RESIDUE (never Tier 1's MATCHED results) and attempts to
resolve a narrow, explicitly-justified subset of it using small, documented
tolerances — never an unrestricted similarity score, never ground truth,
never an LLM.

GUIDING PRINCIPLE (same as Tier 1, extended)
-----------------------------------------------
"An unresolved transaction is better than an incorrect financial match."

Tier 1 asks: "Are these obviously identical?"
Tier 2 asks: "They are not exactly identical, but is there enough explicit,
              structured evidence to safely conclude they are the same
              transaction?"

Tier 2 remains 100% deterministic. Every match is explainable by a named
rule and a small set of concrete evidence fields — never a bare numeric
score.

APPROVED SCOPE (per Phase 4 sign-off — Option B)
-----------------------------------------------------
Tier 2 in this phase implements ONLY:
    - amount tolerance:            <= INR 0.05  (Decimal-based, exact)
    - settlement-date window:      <= 2 days     (supporting evidence only,
                                                    never sufficient alone)
    - explicit reference transformations observed in the real dataset:
          * IDENTITY                             (reference already exact;
                                                    only amount is fuzzy --
                                                    the ROUNDING-case shape)
          * GW{n} <-> PAY{n}                    (prefix swap, same digits)
          * dash-prefix ("PAY-088")              (already collapsed to
                                                    PAY088 by Phase 2's
                                                    normalize_reference();
                                                    reduces to prefix swap)
          * bare numeric suffix ("089")          (bank_reference is just
                                                    the zero-padded digits)
    - a single composite rule requiring reference-transform compatibility
      AND amount within tolerance AND exactly one candidate (date window
      recorded as corroborating evidence when available, never a
      requirement on its own and never sufficient on its own)
    - candidate uniqueness / ambiguity preservation
    - one-to-one protection (layered on top of Tier 1's own consumption)
    - duplicate-ledger protection (never silently pick a duplicate)
    - refund protection (refund rows are never fuzzy-matched to anything)
    - tax/TDS protection (TAX_LINE_MISMATCH is explicitly NOT resolved here)

EXPLICITLY OUT OF SCOPE FOR THIS PHASE (left unresolved, passed forward)
----------------------------------------------------------------------------
    - PARTIAL_REFUND            (no REFUND_LINKED_NET_AMOUNT rule — deferred)
    - TAX_LINE_MISMATCH         (no TDS_LINKED_NET_AMOUNT rule — deferred)
    - DUPLICATE_LEDGER_ENTRY    (ambiguity is preserved, never resolved)
    - NO_BANK_COUNTERPART       (no bank row exists at all — nothing to match)
    - true orphans              (e.g. PAY105 — no legitimate counterpart)
    - the PAY107B decoy         (its only candidate is unavailable — already
                                   consumed by PAY107 at Tier 1)
    - PAY108-111                (Tier 3 LLM-adjudication-designed cases:
                                   ambiguous bank credits, split settlement,
                                   contradictory amount, missing structured
                                   reference resolvable only via free text)

STRICT ARCHITECTURAL BOUNDARY
-------------------------------
Tier 2 DOES:
    - operate ONLY on Tier 1's residue (get_residue() output)
    - respect Tier 1's consumption bookkeeping: any bank/ledger row Tier 1
      already consumed is permanently unavailable to Tier 2
    - apply its own additional one-to-one consumption on top of Tier 1's
    - require candidate uniqueness before ever calling something MATCHED
    - preserve every rejected/ambiguous candidate for audit
    - produce a structured, auditable result compatible with Tier 1's shape

Tier 2 DOES NOT:
    - reprocess or override anything Tier 1 already MATCHED
    - use ground truth to make any matching decision
    - call an LLM, use embeddings, or use any unrestricted similarity score
    - apply amount tolerance to hide a refund or TDS deduction
    - force a match when more than one candidate satisfies the rule
    - fabricate a missing reference
    - attempt split-settlement combination matching
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.normalize import CanonicalRecord
from core.match_exact import Tier1Result, ExactMatcher


# ===========================================================================
# Configuration — explicit, documented, data-justified (see docs/TIER2.md)
# ===========================================================================

# Maximum INR amount difference tolerated as "the same payment, rounded
# differently at the bank's end". Justified by the real ROUNDING cases in
# the Phase 1 dataset (PAY071-077), whose actual diffs range 0.02-0.05.
AMOUNT_TOLERANCE = Decimal("0.05")

# Maximum settlement-date lag treated as legitimate delay. Justified by the
# real SETTLEMENT_DELAY cases (PAY078-085, lag 1-2 days) -- though those
# cases already resolve at Tier 1 (Section 14: Tier 1 doesn't gate on date),
# so in THIS dataset no residue case is resolved by the date window alone.
# It is retained as corroborating evidence for future datasets / robustness,
# per spec Section 11, and is NEVER sufficient by itself.
DATE_WINDOW_DAYS = 2


# ===========================================================================
# Status / rule / reason taxonomy
# ===========================================================================

STATUS_MATCHED = "MATCHED"
STATUS_PARTIAL_MATCH = "PARTIAL_MATCH"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_NO_FUZZY_CANDIDATE = "NO_FUZZY_CANDIDATE"

RULE_PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE = "PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE"

REASON_MULTIPLE_FUZZY_CANDIDATES = "MULTIPLE_FUZZY_CANDIDATES"
REASON_NO_REFERENCE_TRANSFORM_MATCH = "NO_REFERENCE_TRANSFORM_MATCH"
REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE = "REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE"
REASON_NOT_ELIGIBLE_FOR_TIER_2 = "NOT_ELIGIBLE_FOR_TIER_2"
REASON_OUT_OF_SCOPE_CATEGORY = "OUT_OF_SCOPE_FOR_THIS_PHASE"


@dataclass
class Tier2Result:
    """
    One structured decision per Tier-1-residue logical transaction, kept
    shape-compatible with Tier1Result so downstream tooling (evaluation,
    reporting, future Tier 3 input) can treat both uniformly.
    """
    transaction_id: str
    status: str                                # MATCHED | PARTIAL_MATCH | AMBIGUOUS | NO_FUZZY_CANDIDATE
    tier: str                                  # always "TIER_2"
    rule: Optional[str]
    matched_records: dict[str, Optional[str]]  # {"gateway": ..., "bank": ..., "ledger": ...}
    candidate_records: list[dict]              # every candidate considered, matched or not
    evidence: dict
    reason: Optional[str] = None
    decision_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Tier2Summary:
    total_residue_evaluated: int
    matched_count: int
    ambiguous_count: int
    unresolved_count: int  # NO_FUZZY_CANDIDATE + NOT_ELIGIBLE + out-of-scope, i.e. everything not MATCHED/AMBIGUOUS
    match_percentage: float

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# Reference-transform evidence (explicit, closed set — see module docstring)
# ===========================================================================

def _extract_gateway_reference(gw: CanonicalRecord) -> Optional[str]:
    ref = gw.secondary_references.get("gateway_reference")
    return ref.normalized if ref and ref.normalized else None


def _extract_bank_reference(bank: CanonicalRecord) -> Optional[str]:
    ref = bank.secondary_references.get("bank_reference")
    return ref.normalized if ref and ref.normalized else None


def reference_transform_matches(gateway_reference: Optional[str],
                                 bank_reference: Optional[str]) -> bool:
    """
    Returns True only if bank_reference is one of the explicitly-supported
    transformed forms of gateway_reference. This is NOT generic substring
    matching -- each accepted transform is named and closed.

    gateway_reference is expected in the canonical "GW###" form (Phase 2
    normalized). bank_reference is Phase 2's normalized value, which means
    whitespace/case/dash-prefix-collapse has ALREADY happened (see
    core.normalize.normalize_reference) -- so "PAY-088" arrives here as
    "PAY088", i.e. the dash-prefix style has already reduced to the
    prefix-swap style below by the time this function sees it.

    Supported transforms:
        0. IDENTITY:          "GW071" == "GW071"          (reference is
                                                             already exact --
                                                             this is the
                                                             ROUNDING-case
                                                             shape, where the
                                                             only fuzzy
                                                             dimension is
                                                             amount, not
                                                             reference; Tier 1
                                                             rejected these
                                                             purely on exact
                                                             amount mismatch)
        1. PREFIX_SWAP:      "GW086" <-> "PAY086"      (same digit suffix)
        2. BARE_NUMERIC:     "GW089" <-> "089"           (bank dropped the
                                                            prefix entirely,
                                                            kept only the
                                                            zero-padded
                                                            digit suffix)

    Never treats "UNKNOWN" (the genuine unidentified-credit sentinel) as a
    numeric suffix -- "UNKNOWN" simply never matches the numeric regex, so
    no special-case exclusion is needed, but this is verified by dataset
    inspection (see docs/TIER2.md) and by an explicit adversarial test.
    """
    if not gateway_reference or not bank_reference:
        return False

    # Transform 0: IDENTITY -- reference is already exact; only amount is
    # fuzzy (the real-world ROUNDING case shape).
    if bank_reference == gateway_reference:
        return True

    gw_digits = _digit_suffix(gateway_reference, prefix="GW")
    if gw_digits is None:
        return False

    # Transform 1: PREFIX_SWAP -- "GW086" vs "PAY086"
    if bank_reference == f"PAY{gw_digits}":
        return True

    # Transform 2: BARE_NUMERIC -- "GW089" vs "089"
    if bank_reference == gw_digits:
        return True

    return False


def _digit_suffix(reference: str, prefix: str) -> Optional[str]:
    """
    Extracts the digit suffix of a reference string IF it starts with the
    given prefix and the remainder is purely numeric. Returns None
    otherwise (e.g. "GW094-R" is intentionally rejected -- the refund
    suffix marker means this is NOT a plain GW{n} reference).
    """
    if not reference.startswith(prefix):
        return None
    remainder = reference[len(prefix):]
    if remainder.isdigit():
        return remainder
    return None


def _amount_within_tolerance(gw: CanonicalRecord, bank: CanonicalRecord) -> tuple[bool, Decimal]:
    """
    Decimal-precise amount comparison. Returns (within_tolerance, abs_diff).
    Uses Decimal(str(...)) to avoid binary-float artifacts on the already
    2-decimal-rounded floats Phase 2 produced.
    """
    gw_amt = Decimal(str(gw.amount.normalized))
    bank_amt = Decimal(str(bank.amount.normalized))
    diff = abs(gw_amt - bank_amt)
    return diff <= AMOUNT_TOLERANCE, diff


def _date_difference_days(gw: CanonicalRecord, bank: CanonicalRecord) -> Optional[int]:
    if gw.date.normalized is None or bank.date.normalized is None:
        return None
    d1 = datetime.strptime(gw.date.normalized, "%Y-%m-%d")
    d2 = datetime.strptime(bank.date.normalized, "%Y-%m-%d")
    return abs((d2 - d1).days)




# ===========================================================================
# Eligibility: which residue transactions may Tier 2 even attempt?
# ===========================================================================

def _is_eligible_for_tier2(tier1_result: Tier1Result) -> bool:
    """
    Tier 2, in this phase, only attempts to resolve residue transactions
    that:
        - have a gateway record and a ledger record already established by
          Tier 1 (i.e. status == PARTIAL_MATCH with bank missing) -- Tier 2's
          sole job in this phase is to find the missing BANK side using
          tolerance/reference evidence.
        - do NOT already have a bank match from Tier 1 (nothing to add).

    Explicitly NOT eligible (left untouched, reason recorded):
        - UNRESOLVED_FOR_TIER_1 with reason MULTIPLE_EXACT_CANDIDATES
          (DUPLICATE_LEDGER_ENTRY cases -- ambiguity must be preserved, not
          re-attempted with looser rules)
        - UNRESOLVED_FOR_TIER_1 with reason NO_EXACT_CANDIDATE and no ledger
          match at all (true orphans / decoys -- e.g. PAY105, PAY107B)
        - PARTIAL_MATCH where bank IS already present but ledger is missing
          (e.g. PAY110 -- gateway+bank exact, ledger amount genuinely
          conflicts; this is a Tier 3 NEEDS_HUMAN case, not a Tier 2 one,
          and there is no missing SIDE for Tier 2 to search for -- the
          ledger row that exists simply doesn't satisfy Tier 1's exact rule,
          and Tier 2 in this phase has no ledger-side tolerance rule)
    """
    if tier1_result.status != STATUS_PARTIAL_MATCH:
        return False
    if tier1_result.matched_records.get("bank") is not None:
        return False
    if tier1_result.matched_records.get("ledger") is None:
        return False
    return True


# ===========================================================================
# Core Tier 2 matcher
# ===========================================================================

class FuzzyMatcher:
    """
    Stateful matcher enforcing:
        - Tier 1's consumption is respected (never re-offers a bank/ledger
          row Tier 1 already consumed)
        - Tier 2's own one-to-one consumption on top of that
        - candidate uniqueness before any MATCHED verdict
        - deterministic, input-order-independent results

    Only searches for a missing BANK-side candidate for gateway records that
    already have a Tier 1-established ledger match (see
    `_is_eligible_for_tier2`). This mirrors the actual shape of every
    eligible residue case in the real dataset: gateway+ledger present,
    bank missing due to a small rounding difference or a reformatted
    reference.
    """

    def __init__(self, tier1_matcher: ExactMatcher):
        self.tier1_matcher = tier1_matcher
        self.bank_records = list(tier1_matcher.bank_records)
        self.gateway_by_row_id = {r.source_row_id: r for r in tier1_matcher.gateway_records}
        self.ledger_by_row_id = {r.source_row_id: r for r in tier1_matcher.ledger_records}

        # Tier 2's own consumption tracking, layered on top of Tier 1's.
        self._consumed_bank_row_ids: set[str] = set()

    def _available_bank_records(self) -> list[CanonicalRecord]:
        """
        Bank records available to Tier 2: not consumed by Tier 1, and not
        yet consumed by Tier 2 itself this run.
        """
        already_consumed = (
            self.tier1_matcher._consumed_bank_row_ids | self._consumed_bank_row_ids
        )
        return [b for b in self.bank_records if b.source_row_id not in already_consumed]

    def resolve(self, tier1_result: Tier1Result) -> Tier2Result:
        txn_id = tier1_result.transaction_id

        if not _is_eligible_for_tier2(tier1_result):
            return Tier2Result(
                transaction_id=txn_id,
                status=tier1_result.status,  # preserve Tier 1's own status unchanged
                tier="TIER_2",
                rule=None,
                matched_records=dict(tier1_result.matched_records),
                candidate_records=[],
                evidence={"tier1_status": tier1_result.status, "tier1_reason": tier1_result.reason},
                reason=REASON_NOT_ELIGIBLE_FOR_TIER_2,
            )

        gw_row_id = tier1_result.matched_records["gateway"]
        ledger_row_id = tier1_result.matched_records["ledger"]
        gw = self.gateway_by_row_id[gw_row_id]
        gw_reference = _extract_gateway_reference(gw)

        available_bank = self._available_bank_records()

        # Gather all bank candidates whose reference transforms match,
        # regardless of amount -- needed so a "reference matched but amount
        # rejected" case is distinguishable from "no reference match at all"
        # in the evidence trail.
        reference_candidates = [
            b for b in available_bank
            if reference_transform_matches(gw_reference, _extract_bank_reference(b))
        ]

        candidate_records = []
        amount_ok_candidates = []
        for b in reference_candidates:
            within, diff = _amount_within_tolerance(gw, b)
            date_diff = _date_difference_days(gw, b)
            entry = {
                "source": "bank",
                "source_row_id": b.source_row_id,
                "bank_reference": _extract_bank_reference(b),
                "amount": b.amount.normalized,
                "amount_difference": float(diff),
                "within_amount_tolerance": within,
                "date_difference_days": date_diff,
            }
            candidate_records.append(entry)
            if within:
                amount_ok_candidates.append((b, diff, date_diff))

        if not reference_candidates:
            return Tier2Result(
                transaction_id=txn_id,
                status=STATUS_PARTIAL_MATCH,
                tier="TIER_2",
                rule=None,
                matched_records=dict(tier1_result.matched_records),
                candidate_records=[],
                evidence={
                    "gateway_reference": gw_reference,
                    "amount": gw.amount.normalized,
                },
                reason=REASON_NO_REFERENCE_TRANSFORM_MATCH,
            )

        if not amount_ok_candidates:
            return Tier2Result(
                transaction_id=txn_id,
                status=STATUS_PARTIAL_MATCH,
                tier="TIER_2",
                rule=None,
                matched_records=dict(tier1_result.matched_records),
                candidate_records=candidate_records,
                evidence={
                    "gateway_reference": gw_reference,
                    "amount": gw.amount.normalized,
                    "amount_tolerance": float(AMOUNT_TOLERANCE),
                    "reference_candidate_count": len(reference_candidates),
                },
                reason=REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE,
            )

        if len(amount_ok_candidates) > 1:
            return Tier2Result(
                transaction_id=txn_id,
                status=STATUS_AMBIGUOUS,
                tier="TIER_2",
                rule=None,
                matched_records={"gateway": gw_row_id, "bank": None, "ledger": ledger_row_id},
                candidate_records=candidate_records,
                evidence={
                    "gateway_reference": gw_reference,
                    "amount": gw.amount.normalized,
                    "amount_tolerance": float(AMOUNT_TOLERANCE),
                    "candidate_count": len(amount_ok_candidates),
                },
                reason=REASON_MULTIPLE_FUZZY_CANDIDATES,
            )

        # Exactly one candidate satisfies reference-transform AND amount
        # tolerance -> safe to match. Date window is recorded as
        # corroborating evidence only; it does not gate the decision, same
        # as Tier 1's documented treatment of settlement date (Section 14),
        # but we DO surface whether it falls inside the configured window
        # for audit/reporting purposes.
        bank_match, amount_diff, date_diff = amount_ok_candidates[0]
        self._consumed_bank_row_ids.add(bank_match.source_row_id)

        within_date_window = (
            date_diff is not None and date_diff <= DATE_WINDOW_DAYS
        )

        return Tier2Result(
            transaction_id=txn_id,
            status=STATUS_MATCHED,
            tier="TIER_2",
            rule=RULE_PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE,
            matched_records={"gateway": gw_row_id, "bank": bank_match.source_row_id,
                              "ledger": ledger_row_id},
            candidate_records=candidate_records,
            evidence={
                "gateway_reference": gw_reference,
                "bank_reference": _extract_bank_reference(bank_match),
                "amount": gw.amount.normalized,
                "amount_difference": float(amount_diff),
                "amount_tolerance": float(AMOUNT_TOLERANCE),
                "date_difference_days": date_diff,
                "date_window_days": DATE_WINDOW_DAYS,
                "within_date_window": within_date_window,
                "candidate_count": 1,
            },
            reason=None,
        )


# ===========================================================================
# Public entry point
# ===========================================================================

def run_tier2(residue: list[Tier1Result],
              tier1_matcher: ExactMatcher) -> tuple[list[Tier2Result], Tier2Summary]:
    """
    Run Tier 2 deterministic fuzzy/tolerance matching over Tier 1's residue.

    residue: the output of core.match_exact.get_residue(tier1_results).
             MUST be residue only -- Tier 2 never receives or reprocesses
             Tier 1's MATCHED results.
    tier1_matcher: the ExactMatcher instance from run_tier1(..., return_matcher=True),
             used to (a) look up full gateway/ledger/bank CanonicalRecords by
             source_row_id and (b) respect Tier 1's consumption bookkeeping
             so a bank row Tier 1 already claimed can never be reused here.

    Deterministic: iterates residue in the order given, and because every
    eligible transaction in this phase's scope has at most one qualifying
    candidate (verified against the real dataset), result order and content
    do not depend on input order. (See test_match_fuzzy.py for an explicit
    reversed-order regression test.)

    Returns (results, summary). Every residue transaction produces exactly
    one Tier2Result, whether or not Tier 2 could resolve it.
    """
    matcher = FuzzyMatcher(tier1_matcher)
    results = [matcher.resolve(r) for r in residue]

    matched = sum(1 for r in results if r.status == STATUS_MATCHED)
    ambiguous = sum(1 for r in results if r.status == STATUS_AMBIGUOUS)
    total = len(results)
    unresolved = total - matched - ambiguous

    summary = Tier2Summary(
        total_residue_evaluated=total,
        matched_count=matched,
        ambiguous_count=ambiguous,
        unresolved_count=unresolved,
        match_percentage=round((matched / total * 100), 2) if total else 0.0,
    )
    return results, summary


def get_tier2_residue(results: list[Tier2Result]) -> list[Tier2Result]:
    """
    Everything Tier 2 did NOT resolve to MATCHED: AMBIGUOUS and all
    unresolved/ineligible statuses. This is what continues forward to
    Tier 3 (a future phase) -- never modified or interpreted further here.
    """
    return [r for r in results if r.status != STATUS_MATCHED]


# ===========================================================================
# Ground-truth evaluation (evaluation-only — NEVER consulted by matching
# logic above). Mirrors core.match_exact.evaluate_against_ground_truth's
# separation of concerns.
# ===========================================================================

@dataclass
class Tier2Evaluation:
    total_residue_transactions: int
    tier2_expected_count: int          # ground truth rows expecting resolution AT TIER_2
    tier2_correctly_matched: int
    false_matches: list[dict]          # Tier 2 said MATCHED, ground truth disagrees
    missed_tier2_opportunities: list[dict]  # ground truth expects TIER_2 MATCHED, Tier 2 did not
    correctly_deferred: int            # ground truth expects something else, Tier 2 correctly did not match

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_against_ground_truth(results: list[Tier2Result],
                                   ground_truth_rows: list[dict]) -> Tier2Evaluation:
    """
    Compares Tier 2's independently-produced results against
    data/ground_truth.csv, PURELY for reporting. Never called by run_tier2()
    or FuzzyMatcher -- ground truth has zero influence on any Tier 2
    matching decision.
    """
    results_by_txn = {r.transaction_id: r for r in results}
    gt_by_txn = {row["transaction_id"]: row for row in ground_truth_rows}

    false_matches = []
    missed = []
    tier2_expected = 0
    tier2_correct = 0
    correctly_deferred = 0

    for txn_id, result in results_by_txn.items():
        gt_row = gt_by_txn.get(txn_id)
        if gt_row is None:
            continue

        expected_tier = gt_row["expected_matching_tier"]
        expected_status = gt_row["expected_status"]
        is_expected_tier2 = (expected_tier == "TIER_2" and expected_status == "MATCHED")

        if is_expected_tier2:
            tier2_expected += 1

        actual_matched = result.status == STATUS_MATCHED

        if is_expected_tier2:
            if actual_matched:
                tier2_correct += 1
            else:
                missed.append({
                    "transaction_id": txn_id,
                    "expected_category": gt_row["expected_category"],
                    "tier2_actual_status": result.status,
                    "tier2_reason": result.reason,
                })
        else:
            if actual_matched:
                false_matches.append({
                    "transaction_id": txn_id,
                    "expected_category": gt_row["expected_category"],
                    "expected_tier": expected_tier,
                    "tier2_rule": result.rule,
                })
            else:
                correctly_deferred += 1

    return Tier2Evaluation(
        total_residue_transactions=len(results_by_txn),
        tier2_expected_count=tier2_expected,
        tier2_correctly_matched=tier2_correct,
        false_matches=false_matches,
        missed_tier2_opportunities=missed,
        correctly_deferred=correctly_deferred,
    )
