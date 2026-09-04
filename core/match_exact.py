"""
LedgerLoop — Phase 3: Tier 1 Exact Matching
==============================================

Consumes the canonical normalized records produced by Phase 2
(core/normalize.py) and produces deterministic, explainable EXACT matches
across Gateway, Bank, and Ledger — plus an explicit residue of everything
Tier 1 could not confidently resolve.

GUIDING PRINCIPLE
------------------
"Match only when the deterministic evidence is unambiguous."

Tier 1 never guesses. Anything that isn't a clean, unique, exact match falls
through to the residue for Tier 2 (fuzzy/tolerance matching) to attempt.

STRICT ARCHITECTURAL BOUNDARY
-------------------------------
Tier 1 DOES:
    - exact amount comparison (no tolerance)
    - exact normalized-reference comparison (no fuzzy/substring/edit-distance)
    - one-to-one match protection (a source row is consumed at most once)
    - explicit ambiguity detection (multiple exact candidates -> unresolved)
    - preserve which of the three sources were actually found
    - produce a structured, auditable result for every logical transaction

Tier 1 DOES NOT:
    - apply any tolerance to amount or date
    - apply any fuzzy/similarity/substring/edit-distance logic to references
    - call an LLM
    - resolve ambiguity by picking a "best guess"
    - create final exception records
    - modify Phase 1 source data or Phase 2 normalized records
    - use ground_truth.csv to make any matching decision (ground truth is
      strictly an external evaluation input, applied only by the separate
      evaluation function at the bottom of this module — never inside the
      matching logic itself)

ELIGIBLE REFERENCE PAIRS (the ONLY cross-source reference comparisons Tier 1
is allowed to make — see Section 4/9 of the Phase 3 spec)
-------------------------------------------------------------------------------
Inspecting the actual Phase 1/Phase 2 data (not assumed) shows:

    - ledger.payment_reference (canonical: ledger.transaction_reference)
      is the SAME identifier space as gateway.payment_id
      (canonical: gateway.transaction_reference). 116/116 real ledger rows
      confirm payment_reference == some gateway payment_id exactly.
      -> ELIGIBLE: gateway.transaction_reference <-> ledger.transaction_reference

    - bank.bank_reference (canonical: bank.secondary_references["bank_reference"])
      is the bank's copy of gateway.gateway_reference
      (canonical: gateway.secondary_references["gateway_reference"]) — e.g.
      bank_reference "GW093" pairs with gateway_reference "GW093", NOT with
      gateway payment_id "PAY093".
      -> ELIGIBLE: gateway.secondary_references["gateway_reference"]
                   <-> bank.secondary_references["bank_reference"]

NOT eligible for Tier 1 (never compared as if equivalent):
    - bank.transaction_reference (bank_transaction_id) vs anything gateway/ledger
    - bank.secondary_references["utr"] vs anything gateway/ledger
    - any cross-comparison that would require truncation-awareness, fuzzy
      matching, or free-text interpretation (e.g. bank "description")

The logical transaction anchor is the GATEWAY payment_id. Every Tier 1
result is keyed by it. A bank or ledger record that has no eligible
reference match to any gateway payment_id cannot become a Tier 1
"matched_records" member — at most it appears in `evidence` if directly
useful, otherwise it stays in the residue for later tiers.

SETTLEMENT DATE (Section 14)
------------------------------
Tier 1 does NOT require the gateway payment_date and bank date to be
identical for a match to fire. If reference + amount are exact, a date
difference does not block the match — it is simply preserved as evidence
(`evidence["date_difference_days"]`) for the audit trail and for later
tiers/exception review. No fuzzy date WINDOW logic is implemented here;
Tier 1 does not decide "is this date difference acceptable" — it just
records the fact and always matches on reference+amount alone. This
matches the Phase 1 SETTLEMENT_DELAY ground-truth category, which expects
these to resolve via TIER_2 in general, but Tier 1 restricting on date
would be introducing an undocumented tolerance rule; we instead let the
one-to-one + exact-reference protections be the sole strictness mechanism,
and rely on evaluation-against-ground-truth (Section 18) to characterize
how often this happens rather than hard-coding a date check into the
matching rule itself. See `evaluate_against_ground_truth()` for how this
plays out in measured Tier 1 performance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from core.normalize import CanonicalRecord, normalize_all, AllSourcesNormalizationResult


# ===========================================================================
# Result structures
# ===========================================================================

# Status taxonomy (Section 6/10) — documented explicitly, never silently blended.
STATUS_MATCHED = "MATCHED"                          # gateway + bank + ledger all found
STATUS_PARTIAL_MATCH = "PARTIAL_MATCH"               # 2 of 3 sources found, unambiguously
STATUS_UNRESOLVED_FOR_TIER_1 = "UNRESOLVED_FOR_TIER_1"  # ambiguous or insufficient evidence

REASON_MULTIPLE_EXACT_CANDIDATES = "MULTIPLE_EXACT_CANDIDATES"
REASON_NO_EXACT_CANDIDATE = "NO_EXACT_CANDIDATE"
REASON_GATEWAY_ONLY = "GATEWAY_ONLY"  # no eligible bank or ledger candidate at all
REASON_CONTENDED_BY_ANOTHER_GATEWAY_RECORD = "CONTENDED_BY_ANOTHER_GATEWAY_RECORD"

RULE_EXACT_REFERENCE_AND_AMOUNT = "EXACT_REFERENCE_AND_AMOUNT"
RULE_EXACT_GATEWAY_REFERENCE_AND_AMOUNT = "EXACT_GATEWAY_REFERENCE_AND_AMOUNT"


@dataclass
class Tier1Result:
    """
    One structured decision per logical transaction (keyed by gateway
    payment_id). Every field required by Phase 3 Section 15/21 is present.
    """
    transaction_id: str                       # gateway transaction_reference.normalized
    status: str                                # MATCHED | PARTIAL_MATCH | UNRESOLVED_FOR_TIER_1
    tier: str                                  # always "TIER_1" for this module's output
    rule: Optional[str]                        # which Tier 1 rule fired, or None if unresolved
    confidence: float                          # 1.0 for any Tier 1 match, 0.0 if unresolved
    matched_records: dict[str, Optional[str]]  # {"gateway": "G001", "bank": "B001", "ledger": "L001" or None}
    unmatched_candidates: list[dict]           # candidate source rows considered but not chosen (for ambiguity/audit)
    evidence: dict                             # reference/amount/date evidence backing the decision
    reason: Optional[str] = None               # populated when status != MATCHED (e.g. MULTIPLE_EXACT_CANDIDATES)
    decision_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Tier1Summary:
    """Aggregate Tier 1 run statistics (Section 18) — Tier 1 performance only, never a final system metric."""
    total_logical_transactions: int
    matched_count: int
    partial_match_count: int
    unresolved_count: int
    match_percentage: float  # matched_count / total_logical_transactions * 100

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# Candidate indexing helpers
# ===========================================================================

def _index_by_reference(records: list[CanonicalRecord], ref_getter) -> dict[str, list[CanonicalRecord]]:
    """
    Build {normalized_reference: [records]} using ref_getter(record) to pull
    the relevant Reference field. Records whose reference is None (missing)
    are excluded from the index entirely — Tier 1 never matches on an absent
    reference (that would not be "unambiguous deterministic evidence").
    """
    index: dict[str, list[CanonicalRecord]] = defaultdict(list)
    for r in records:
        ref = ref_getter(r)
        if ref is not None and ref.normalized:
            index[ref.normalized].append(r)
    return index


def _amount_matches(a: CanonicalRecord, b: CanonicalRecord) -> bool:
    """EXACT amount comparison only — see Section 8. No tolerance, no re-rounding."""
    if a.amount.normalized is None or b.amount.normalized is None:
        return False
    return a.amount.normalized == b.amount.normalized


def _date_difference_days(a: CanonicalRecord, b: CanonicalRecord) -> Optional[int]:
    """
    Informational only (Section 14) — never used to gate a Tier 1 decision.
    Returns None if either date failed to normalize.
    """
    if a.date.normalized is None or b.date.normalized is None:
        return None
    da = datetime.strptime(a.date.normalized, "%Y-%m-%d")
    db = datetime.strptime(b.date.normalized, "%Y-%m-%d")
    return abs((db - da).days)


# ===========================================================================
# Core Tier 1 matcher
# ===========================================================================

class ExactMatcher:
    """
    Stateful matcher enforcing one-to-one consumption (Section 7): once a
    bank or ledger record is consumed by a valid match, it is removed from
    the candidate pool and cannot be reused by a later logical transaction.

    Processing order is deterministic: gateway records are processed in the
    order Phase 2 produced them (which is itself the order Phase 1 wrote
    gateway.csv), so re-running this matcher on the same input always
    produces the same output (Section 22 — reproducibility).

    ORDER-INDEPENDENCE OF AMBIGUITY DETECTION
    -------------------------------------------
    A subtler one-to-one hazard than "one bank row, two ledger rows" (Section
    10/11) is: two DIFFERENT gateway records competing for the SAME bank or
    ledger candidate (e.g. a gateway-side data quality issue producing a
    duplicate gateway_reference). If ambiguity were only checked against the
    *currently available* pool at the moment each gateway record is
    processed, the first-processed gateway record would silently "win" the
    shared candidate and look like a confident, unambiguous match — while
    the second-processed one would incorrectly report "no candidate at all"
    instead of "the candidate that existed was already claimed by an equally
    valid competitor". That is exactly the "confidently wrong" failure mode
    Section 20 warns against, and it would make Tier 1's output silently
    depend on row processing order, violating Section 22 reproducibility-of-
    meaning (even though the mechanical output would still be deterministic,
    its correctness would depend on incidental CSV row order).

    To prevent this, ambiguity is computed as a GLOBAL, order-independent
    property at construction time: for each bank/ledger reference key, if
    MORE THAN ONE gateway record's own reference maps to it, every one of
    those gateway records is flagged as contending for a shared candidate
    and is routed to UNRESOLVED_FOR_TIER_1 / MULTIPLE_EXACT_CANDIDATES
    up front — none of them silently consumes it. This is checked in
    addition to (not instead of) the existing "multiple bank/ledger rows for
    one gateway reference" ambiguity check.
    """

    def __init__(self, normalized: AllSourcesNormalizationResult):
        self.gateway_records = list(normalized.gateway.records)
        self.bank_records = list(normalized.bank.records)
        self.ledger_records = list(normalized.ledger.records)

        # Index bank records by their ELIGIBLE reference: bank_reference
        # (bank's copy of the gateway_reference). NOT bank_transaction_id,
        # NOT utr — see module docstring "ELIGIBLE REFERENCE PAIRS".
        self._bank_by_bank_reference = _index_by_reference(
            self.bank_records, lambda r: r.secondary_references.get("bank_reference")
        )

        # Index ledger records by their ELIGIBLE reference: payment_reference
        # (canonical transaction_reference), which lives in the same
        # identifier space as gateway payment_id.
        self._ledger_by_payment_reference = _index_by_reference(
            self.ledger_records, lambda r: r.transaction_reference
        )

        # Consumption tracking (one-to-one protection, Section 7).
        self._consumed_bank_row_ids: set[str] = set()
        self._consumed_ledger_row_ids: set[str] = set()

        # Global, order-independent contention detection (see class
        # docstring above): count how many DISTINCT gateway records' own
        # reference maps to each bank/ledger reference key, computed once,
        # up front, before any consumption occurs.
        self._gateway_contenders_per_bank_ref: dict[str, int] = defaultdict(int)
        self._gateway_contenders_per_ledger_ref: dict[str, int] = defaultdict(int)
        for gw in self.gateway_records:
            gw_ref = gw.secondary_references.get("gateway_reference")
            if gw_ref is not None and gw_ref.normalized:
                self._gateway_contenders_per_bank_ref[gw_ref.normalized] += 1
            txn_ref = gw.transaction_reference
            if txn_ref is not None and txn_ref.normalized:
                self._gateway_contenders_per_ledger_ref[txn_ref.normalized] += 1

    # -- candidate lookup, filtered to not-yet-consumed rows ---------------

    def _available_bank_candidates(self, gateway_reference_normalized: Optional[str]) -> list[CanonicalRecord]:
        if not gateway_reference_normalized:
            return []
        candidates = self._bank_by_bank_reference.get(gateway_reference_normalized, [])
        return [c for c in candidates if c.source_row_id not in self._consumed_bank_row_ids]

    def _available_ledger_candidates(self, payment_id_normalized: Optional[str]) -> list[CanonicalRecord]:
        if not payment_id_normalized:
            return []
        candidates = self._ledger_by_payment_reference.get(payment_id_normalized, [])
        return [c for c in candidates if c.source_row_id not in self._consumed_ledger_row_ids]

    # -- main entry point ----------------------------------------------------

    def run(self) -> list[Tier1Result]:
        results: list[Tier1Result] = []
        for gw in self.gateway_records:
            results.append(self._resolve_one(gw))
        return results

    def _resolve_one(self, gw: CanonicalRecord) -> Tier1Result:
        txn_id = gw.transaction_reference.normalized
        gw_ref = gw.secondary_references.get("gateway_reference")
        gw_ref_normalized = gw_ref.normalized if gw_ref else None

        # ---- gather amount-AND-reference-exact candidates on each side ----
        bank_ref_candidates = self._available_bank_candidates(gw_ref_normalized)
        bank_exact = [c for c in bank_ref_candidates if _amount_matches(gw, c)]

        ledger_ref_candidates = self._available_ledger_candidates(txn_id)
        ledger_exact = [c for c in ledger_ref_candidates if _amount_matches(gw, c)]

        # ---- ambiguity check: multiple exact candidates on EITHER side ----
        # Section 10/11: never force a choice among equally-valid candidates,
        # including the deliberate duplicate-ledger-entry scenario.
        if len(bank_exact) > 1 or len(ledger_exact) > 1:
            return self._unresolved_multiple_candidates(
                gw, txn_id, gw_ref_normalized, bank_exact, ledger_exact,
                bank_ref_candidates, ledger_ref_candidates,
            )

        # ---- gateway-side contention check (see class docstring) ----
        # Even if exactly one candidate is currently available on a side,
        # that candidate is only SAFELY claimable if this gateway record is
        # the ONLY gateway record contending for it. If another gateway
        # record's reference maps to the same key, the two gateway records
        # are competing for one shared candidate — order must not silently
        # decide the winner. This is checked independently per side (a
        # transaction may be uniquely determined on one side but contested
        # on the other).
        bank_contended = (
            len(bank_exact) == 1
            and gw_ref_normalized is not None
            and self._gateway_contenders_per_bank_ref[gw_ref_normalized] > 1
        )
        ledger_contended = (
            len(ledger_exact) == 1
            and txn_id is not None
            and self._gateway_contenders_per_ledger_ref[txn_id] > 1
        )
        if bank_contended or ledger_contended:
            return self._unresolved_gateway_side_contention(
                gw, txn_id, gw_ref_normalized, bank_exact if bank_contended else [],
                ledger_exact if ledger_contended else [],
            )

        bank_match = bank_exact[0] if len(bank_exact) == 1 else None
        ledger_match = ledger_exact[0] if len(ledger_exact) == 1 else None

        # ---- no eligible candidate on either side: gateway-only residue ----
        if bank_match is None and ledger_match is None:
            return self._unresolved_no_candidate(gw, txn_id, gw_ref_normalized)

        # ---- consume matched records (one-to-one protection) ----
        if bank_match is not None:
            self._consumed_bank_row_ids.add(bank_match.source_row_id)
        if ledger_match is not None:
            self._consumed_ledger_row_ids.add(ledger_match.source_row_id)

        status = STATUS_MATCHED if (bank_match is not None and ledger_match is not None) \
            else STATUS_PARTIAL_MATCH

        rule = RULE_EXACT_REFERENCE_AND_AMOUNT if ledger_match is not None \
            else RULE_EXACT_GATEWAY_REFERENCE_AND_AMOUNT

        evidence = {
            "gateway_reference_used": txn_id,
            "amount": gw.amount.normalized,
        }
        if bank_match is not None:
            evidence["gateway_reference_to_bank_reference"] = gw_ref_normalized
            date_diff = _date_difference_days(gw, bank_match)
            evidence["date_difference_days"] = date_diff
        if ledger_match is not None:
            evidence["ledger_payment_reference"] = ledger_match.transaction_reference.normalized

        return Tier1Result(
            transaction_id=txn_id,
            status=status,
            tier="TIER_1",
            rule=rule,
            confidence=1.0,
            matched_records={
                "gateway": gw.source_row_id,
                "bank": bank_match.source_row_id if bank_match else None,
                "ledger": ledger_match.source_row_id if ledger_match else None,
            },
            unmatched_candidates=[],
            evidence=evidence,
        )

    def _unresolved_multiple_candidates(
        self, gw: CanonicalRecord, txn_id: str, gw_ref_normalized: Optional[str],
        bank_exact: list[CanonicalRecord], ledger_exact: list[CanonicalRecord],
        bank_ref_candidates: list[CanonicalRecord], ledger_ref_candidates: list[CanonicalRecord],
    ) -> Tier1Result:
        candidate_descriptions = []
        for c in bank_exact:
            candidate_descriptions.append({
                "source": "bank", "source_row_id": c.source_row_id,
                "reference": c.secondary_references["bank_reference"].normalized,
                "amount": c.amount.normalized,
            })
        for c in ledger_exact:
            candidate_descriptions.append({
                "source": "ledger", "source_row_id": c.source_row_id,
                "reference": c.transaction_reference.normalized,
                "amount": c.amount.normalized,
            })

        return Tier1Result(
            transaction_id=txn_id,
            status=STATUS_UNRESOLVED_FOR_TIER_1,
            tier="TIER_1",
            rule=None,
            confidence=0.0,
            matched_records={"gateway": gw.source_row_id, "bank": None, "ledger": None},
            unmatched_candidates=candidate_descriptions,
            evidence={
                "gateway_reference_used": txn_id,
                "amount": gw.amount.normalized,
                "bank_candidate_count": len(bank_exact),
                "ledger_candidate_count": len(ledger_exact),
            },
            reason=REASON_MULTIPLE_EXACT_CANDIDATES,
        )

    def _unresolved_no_candidate(
        self, gw: CanonicalRecord, txn_id: str, gw_ref_normalized: Optional[str],
    ) -> Tier1Result:
        return Tier1Result(
            transaction_id=txn_id,
            status=STATUS_UNRESOLVED_FOR_TIER_1,
            tier="TIER_1",
            rule=None,
            confidence=0.0,
            matched_records={"gateway": gw.source_row_id, "bank": None, "ledger": None},
            unmatched_candidates=[],
            evidence={
                "gateway_reference_used": txn_id,
                "amount": gw.amount.normalized,
                "gateway_reference_for_bank_lookup": gw_ref_normalized,
            },
            reason=REASON_NO_EXACT_CANDIDATE if gw_ref_normalized else REASON_GATEWAY_ONLY,
        )

    def _unresolved_gateway_side_contention(
        self, gw: CanonicalRecord, txn_id: str, gw_ref_normalized: Optional[str],
        contended_bank: list[CanonicalRecord], contended_ledger: list[CanonicalRecord],
    ) -> Tier1Result:
        """
        Fires when this gateway record's only available bank and/or ledger
        candidate is ALSO reachable by at least one other gateway record
        (see ExactMatcher class docstring). Neither gateway record may claim
        the shared candidate via Tier 1 — both must be left for Tier 2/3 or
        human review, since exact-match evidence alone cannot disambiguate
        which gateway record the shared candidate actually belongs to.
        """
        candidate_descriptions = []
        for c in contended_bank:
            candidate_descriptions.append({
                "source": "bank", "source_row_id": c.source_row_id,
                "reference": c.secondary_references["bank_reference"].normalized,
                "amount": c.amount.normalized,
                "contended": True,
            })
        for c in contended_ledger:
            candidate_descriptions.append({
                "source": "ledger", "source_row_id": c.source_row_id,
                "reference": c.transaction_reference.normalized,
                "amount": c.amount.normalized,
                "contended": True,
            })

        return Tier1Result(
            transaction_id=txn_id,
            status=STATUS_UNRESOLVED_FOR_TIER_1,
            tier="TIER_1",
            rule=None,
            confidence=0.0,
            matched_records={"gateway": gw.source_row_id, "bank": None, "ledger": None},
            unmatched_candidates=candidate_descriptions,
            evidence={
                "gateway_reference_used": txn_id,
                "amount": gw.amount.normalized,
                "gateway_reference_for_bank_lookup": gw_ref_normalized,
                "contending_gateway_count_bank": (
                    self._gateway_contenders_per_bank_ref.get(gw_ref_normalized, 0)
                    if gw_ref_normalized else 0
                ),
                "contending_gateway_count_ledger": (
                    self._gateway_contenders_per_ledger_ref.get(txn_id, 0) if txn_id else 0
                ),
            },
            reason=REASON_CONTENDED_BY_ANOTHER_GATEWAY_RECORD,
        )


# ===========================================================================
# Public entry point
# ===========================================================================

def run_tier1(normalized: Optional[AllSourcesNormalizationResult] = None,
              data_dir: str = "data",
              return_matcher: bool = False):
    """
    Run Tier 1 exact matching end-to-end.

    If `normalized` is not supplied, this calls Phase 2's normalize_all()
    itself (non-strict) against `data_dir`. Passing a pre-built
    AllSourcesNormalizationResult lets callers/tests reuse one normalization
    pass across multiple matcher runs without re-parsing CSVs.

    Returns (results, summary) by default. If return_matcher=True, returns
    (results, summary, matcher) so callers can also inspect
    get_unclaimed_source_records(matcher) for gateway-invisible bank/ledger
    residue (e.g. true bank-only orphans).

    Deterministic: running this twice on the same input produces identical
    results (same order, same decisions) — no LLM calls, no randomness, no
    wall-clock-dependent logic other than the informational `decision_time`
    timestamp field, which does not affect any decision.
    """
    if normalized is None:
        normalized = normalize_all(data_dir=data_dir, strict=False)

    matcher = ExactMatcher(normalized)
    results = matcher.run()

    matched = sum(1 for r in results if r.status == STATUS_MATCHED)
    partial = sum(1 for r in results if r.status == STATUS_PARTIAL_MATCH)
    unresolved = sum(1 for r in results if r.status == STATUS_UNRESOLVED_FOR_TIER_1)
    total = len(results)

    summary = Tier1Summary(
        total_logical_transactions=total,
        matched_count=matched,
        partial_match_count=partial,
        unresolved_count=unresolved,
        match_percentage=round((matched / total * 100), 2) if total else 0.0,
    )
    if return_matcher:
        return results, summary, matcher
    return results, summary


def get_residue(results: list[Tier1Result]) -> list[Tier1Result]:
    """
    Everything Tier 1 could NOT confidently resolve to a full 3-way MATCHED
    outcome: both PARTIAL_MATCH and UNRESOLVED_FOR_TIER_1 flow forward to
    Tier 2 (Section 16 — "residue", not a final exception queue). A
    PARTIAL_MATCH is real, useful evidence, but Tier 1's job is confident
    EXACT 3-source resolution, so anything short of that is handed onward
    for Tier 2 to attempt to complete or explain (e.g. NO_BANK_COUNTERPART-
    style cases resolve into PARTIAL_MATCH here, and Tier 2/later phases
    decide whether that partial state is itself the final, correct answer).
    """
    return [r for r in results if r.status != STATUS_MATCHED]


def get_unclaimed_source_records(matcher: ExactMatcher) -> dict[str, list[str]]:
    """
    Bank/ledger residue that is gateway-invisible: Tier 1 is gateway-anchored
    (every Tier1Result is keyed by a gateway payment_id), so a bank or
    ledger row with NO eligible reference match to any gateway payment_id at
    all (e.g. a true bank-only orphan such as Phase 1's PAY106/"UNKNOWN"
    case) never becomes part of any Tier1Result and would otherwise be
    invisible to a caller who only looks at run_tier1()'s return value.

    Call this AFTER matcher.run() has already executed (i.e. after
    consumption bookkeeping is final) to get the full list of bank/ledger
    source_row_ids that were never claimed by any Tier 1 match, for any
    reason — no eligible reference, ambiguous candidate, or amount
    mismatch. This is purely descriptive residue information for Phase 4;
    it makes no additional matching decision.
    """
    return {
        "bank": [r.source_row_id for r in matcher.bank_records
                 if r.source_row_id not in matcher._consumed_bank_row_ids],
        "ledger": [r.source_row_id for r in matcher.ledger_records
                   if r.source_row_id not in matcher._consumed_ledger_row_ids],
    }


# ===========================================================================
# Ground-truth evaluation (Section 17/18) — evaluation-only, NEVER consulted
# by the matching logic above. This function is called strictly AFTER
# run_tier1() has already produced its results.
# ===========================================================================

@dataclass
class Tier1Evaluation:
    total_ground_truth_transactions: int
    tier1_expected_count: int          # ground truth rows expecting TIER_1
    tier1_correctly_matched: int       # Tier 1 MATCHED, and ground truth agrees (TIER_1 + MATCHED)
    false_matches: list[dict]          # Tier 1 said MATCHED, but ground truth disagrees
    missed_tier1_opportunities: list[dict]  # ground truth says TIER_1, but Tier 1 did not MATCH
    correctly_deferred: int            # ground truth expects TIER_2/TIER_3/N-A, Tier 1 correctly did not MATCH

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_against_ground_truth(results: list[Tier1Result], ground_truth_rows: list[dict]) -> Tier1Evaluation:
    """
    Compares Tier 1's independently-produced results against
    data/ground_truth.csv, PURELY for reporting. This function is never
    called by run_tier1() or ExactMatcher — ground truth has zero influence
    on any matching decision (Section 17).

    ground_truth_rows: list of dicts as read by csv.DictReader from
    data/ground_truth.csv (columns: transaction_id, expected_status,
    expected_category, expected_matching_tier, ...).
    """
    results_by_txn = {r.transaction_id: r for r in results}
    gt_by_txn = {row["transaction_id"]: row for row in ground_truth_rows}

    false_matches = []
    missed = []
    tier1_expected = 0
    tier1_correct = 0
    correctly_deferred = 0

    for txn_id, gt_row in gt_by_txn.items():
        expected_tier = gt_row["expected_matching_tier"]
        expected_status = gt_row["expected_status"]
        result = results_by_txn.get(txn_id)

        is_expected_tier1 = (expected_tier == "TIER_1" and expected_status == "MATCHED")
        if is_expected_tier1:
            tier1_expected += 1

        actual_matched = result is not None and result.status == STATUS_MATCHED

        if is_expected_tier1:
            if actual_matched:
                tier1_correct += 1
            else:
                missed.append({
                    "transaction_id": txn_id,
                    "expected_category": gt_row["expected_category"],
                    "tier1_actual_status": result.status if result else "NOT_FOUND",
                    "tier1_reason": result.reason if result else None,
                })
        else:
            # Ground truth expects something OTHER than a clean Tier 1 match
            # (Tier 2, Tier 3, or an exception category). If Tier 1 matched
            # it anyway, that is a FALSE MATCH — Tier 1 was overconfident.
            if actual_matched:
                false_matches.append({
                    "transaction_id": txn_id,
                    "expected_category": gt_row["expected_category"],
                    "expected_tier": expected_tier,
                    "tier1_rule": result.rule,
                })
            else:
                correctly_deferred += 1

    return Tier1Evaluation(
        total_ground_truth_transactions=len(gt_by_txn),
        tier1_expected_count=tier1_expected,
        tier1_correctly_matched=tier1_correct,
        false_matches=false_matches,
        missed_tier1_opportunities=missed,
        correctly_deferred=correctly_deferred,
    )
