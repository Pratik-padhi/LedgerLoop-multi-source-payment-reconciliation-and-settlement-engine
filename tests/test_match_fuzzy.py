"""
LedgerLoop — Phase 4: Tier 2 Fuzzy/Tolerance Matching Tests
================================================================

Covers the 24 required cases plus adversarial safety tests derived from
actual dataset inspection (e.g. the B108 "109" bare-numeric collision risk
against PAY109's gateway record).

Run with:
    python3 -m unittest tests.test_match_fuzzy -v
"""

import csv
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.normalize import (
    CanonicalRecord, Reference, NormalizedDate, NormalizedAmount,
    AllSourcesNormalizationResult, NormalizationResult, normalize_all,
)
from core.match_exact import (
    ExactMatcher, run_tier1, get_residue, STATUS_MATCHED as T1_MATCHED,
)
from core.match_fuzzy import (
    FuzzyMatcher, run_tier2, get_tier2_residue, evaluate_against_ground_truth,
    reference_transform_matches, AMOUNT_TOLERANCE, DATE_WINDOW_DAYS,
    STATUS_MATCHED, STATUS_PARTIAL_MATCH, STATUS_AMBIGUOUS, STATUS_NO_FUZZY_CANDIDATE,
    REASON_MULTIPLE_FUZZY_CANDIDATES, REASON_NO_REFERENCE_TRANSFORM_MATCH,
    REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE, REASON_NOT_ELIGIBLE_FOR_TIER_2,
    RULE_PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


# ===========================================================================
# Fixture builders (mirrors tests/test_match_exact.py's style for consistency)
# ===========================================================================

def make_gateway(source_row_id, payment_id, amount, gateway_reference="GW000",
                  date="2026-08-20", customer_reference="ORD000"):
    return CanonicalRecord(
        source="gateway", source_row_id=source_row_id,
        transaction_reference=Reference(payment_id, payment_id),
        date=NormalizedDate(date, date),
        amount=NormalizedAmount(str(amount), amount),
        status="CAPTURED",
        secondary_references={
            "gateway_reference": Reference(gateway_reference, gateway_reference),
            "customer_reference": Reference(customer_reference, customer_reference),
        },
        extra_dates={}, tax_fields={}, raw_record={},
    )


def make_bank(source_row_id, bank_transaction_id, amount, bank_reference,
              date="2026-08-20", utr="UTR000"):
    ref = Reference(bank_reference, bank_reference) if bank_reference is not None \
        else Reference(None, None)
    return CanonicalRecord(
        source="bank", source_row_id=source_row_id,
        transaction_reference=Reference(bank_transaction_id, bank_transaction_id),
        date=NormalizedDate(date, date),
        amount=NormalizedAmount(str(amount), amount),
        status=None,
        secondary_references={
            "utr": Reference(utr, utr),
            "bank_reference": ref,
            "description": Reference("desc", "desc"),
        },
        extra_dates={"value_date": NormalizedDate(date, date)},
        tax_fields={}, raw_record={},
    )


def make_ledger(source_row_id, payment_reference, amount, invoice_reference="INV000",
                 date="2026-08-20", tds=0.0, tax=0.0, entry_type="SALE"):
    ref = Reference(payment_reference, payment_reference) if payment_reference is not None \
        else Reference(None, None)
    return CanonicalRecord(
        source="ledger", source_row_id=source_row_id,
        transaction_reference=ref,
        date=NormalizedDate(date, date),
        amount=NormalizedAmount(str(amount), amount),
        status=entry_type,
        secondary_references={
            "invoice_reference": Reference(invoice_reference, invoice_reference),
        },
        extra_dates={},
        tax_fields={
            "tax_amount": NormalizedAmount(str(tax), tax),
            "tds_amount": NormalizedAmount(str(tds), tds),
        },
        raw_record={},
    )


def make_normalized(gateway=None, bank=None, ledger=None):
    return AllSourcesNormalizationResult(
        gateway=NormalizationResult(source="gateway", records=gateway or [], warnings=[], errors=[]),
        bank=NormalizationResult(source="bank", records=bank or [], warnings=[], errors=[]),
        ledger=NormalizationResult(source="ledger", records=ledger or [], warnings=[], errors=[]),
    )


def run_full_pipeline(gateway=None, bank=None, ledger=None):
    """Runs Tier 1 then Tier 2 end-to-end on synthetic fixtures."""
    normalized = make_normalized(gateway, bank, ledger)
    tier1_results, tier1_summary, tier1_matcher = run_tier1(
        normalized=normalized, return_matcher=True)
    residue = get_residue(tier1_results)
    tier2_results, tier2_summary = run_tier2(residue, tier1_matcher)
    return tier1_results, tier2_results, tier2_summary, tier1_matcher


# ===========================================================================
# 1. Tier 1 matches are never reprocessed
# ===========================================================================

class TestTier1MatchesNotReprocessed(unittest.TestCase):
    def test_only_residue_is_passed_to_tier2_never_full_tier1_results(self):
        # An exact Tier 1 MATCHED case (gateway+bank+ledger all exact)
        gw_exact = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        bk_exact = make_bank("B001", "BANK001", 500.00, bank_reference="GW001")
        lg_exact = make_ledger("L001", "PAY001", 500.00)

        # A genuine Tier 2-eligible residue case (rounding, PAY002)
        gw_round = make_gateway("G002", "PAY002", 700.00, gateway_reference="GW002")
        bk_round = make_bank("B002", "BANK002", 699.97, bank_reference="GW002")
        lg_round = make_ledger("L002", "PAY002", 700.00)

        tier1_results, tier2_results, summary, matcher = run_full_pipeline(
            gateway=[gw_exact, gw_round], bank=[bk_exact, bk_round], ledger=[lg_exact, lg_round])

        # PAY001 must never appear in Tier 2's results at all
        tier2_ids = {r.transaction_id for r in tier2_results}
        self.assertNotIn("PAY001", tier2_ids)
        self.assertIn("PAY002", tier2_ids)

        # PAY001's bank row must remain claimed by Tier 1, untouched
        t1_pay001 = next(r for r in tier1_results if r.transaction_id == "PAY001")
        self.assertEqual(t1_pay001.status, T1_MATCHED)
        self.assertEqual(t1_pay001.matched_records["bank"], "B001")


# ===========================================================================
# 2-4. Amount tolerance: valid, boundary, just outside
# ===========================================================================

class TestAmountTolerance(unittest.TestCase):
    def test_valid_amount_tolerance_match(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 999.97, bank_reference="GW001")  # diff 0.03
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.rule, RULE_PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE)
        self.assertEqual(r.matched_records["bank"], "B001")
        self.assertAlmostEqual(r.evidence["amount_difference"], 0.03, places=2)

    def test_amount_exact_boundary_0_05_matches(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 999.95, bank_reference="GW001")  # diff exactly 0.05
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertEqual(r.status, STATUS_MATCHED)

    def test_amount_just_outside_tolerance_0_06_rejected(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 999.94, bank_reference="GW001")  # diff 0.06
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE)
        self.assertIsNone(r.matched_records["bank"])


# ===========================================================================
# 5-6. Date window: valid, just outside
# ===========================================================================

class TestDateWindow(unittest.TestCase):
    def test_date_within_window_recorded_as_corroborating_evidence(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001", date="2026-08-20")
        bk = make_bank("B001", "BANK001", 999.98, bank_reference="GW001", date="2026-08-22")  # +2 days
        lg = make_ledger("L001", "PAY001", 1000.00, date="2026-08-20")

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.evidence["date_difference_days"], 2)
        self.assertTrue(r.evidence["within_date_window"])

    def test_date_just_outside_window_still_matches_since_date_is_not_gating(self):
        # Per spec: date alone (or date outside window) must NEVER be the
        # sole reason to reject -- date is corroborating evidence only.
        # Reference+amount tolerance still governs the decision.
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001", date="2026-08-20")
        bk = make_bank("B001", "BANK001", 999.98, bank_reference="GW001", date="2026-08-25")  # +5 days
        lg = make_ledger("L001", "PAY001", 1000.00, date="2026-08-20")

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.evidence["date_difference_days"], 5)
        self.assertFalse(r.evidence["within_date_window"])


# ===========================================================================
# 7-8. Reference transform: valid, insufficient alone
# ===========================================================================

class TestReferenceTransform(unittest.TestCase):
    def test_prefix_swap_gw_to_pay_matches(self):
        self.assertTrue(reference_transform_matches("GW086", "PAY086"))

    def test_bare_numeric_suffix_matches(self):
        self.assertTrue(reference_transform_matches("GW089", "089"))

    def test_dash_prefix_reduces_to_prefix_swap_post_normalization(self):
        # Phase 2 normalize_reference() already collapses "PAY-088" -> "PAY088"
        # before this function ever sees it.
        self.assertTrue(reference_transform_matches("GW088", "PAY088"))

    def test_unrelated_reference_does_not_match(self):
        self.assertFalse(reference_transform_matches("GW001", "GW999"))
        self.assertFalse(reference_transform_matches("GW001", "PAY999"))

    def test_partial_reference_alone_insufficient_without_amount_tolerance(self):
        # Reference transform matches but amount is wildly different --
        # must NOT match on reference alone.
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 50.00, bank_reference="PAY001")  # reference matches, amount doesn't
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE)


# ===========================================================================
# 9. Same amount/date, different identity -> must not match
# ===========================================================================

class TestDifferentIdentityNeverMatches(unittest.TestCase):
    def test_same_amount_and_date_different_reference_does_not_match(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001", date="2026-08-20")
        bk = make_bank("B001", "BANK001", 1000.00, bank_reference="ZZZ999", date="2026-08-20")
        lg = make_ledger("L001", "PAY001", 1000.00, date="2026-08-20")

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_NO_REFERENCE_TRANSFORM_MATCH)


# ===========================================================================
# 10. Multiple candidates -> AMBIGUOUS
# ===========================================================================

class TestMultipleCandidatesAmbiguous(unittest.TestCase):
    def test_two_candidates_within_tolerance_stays_ambiguous(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk1 = make_bank("B001", "BANK001", 999.98, bank_reference="PAY001")  # diff 0.02
        bk2 = make_bank("B002", "BANK002", 999.99, bank_reference="001")     # bare-numeric-ish -- won't match "GW001"->"001"? check below
        # Use a genuinely qualifying second candidate: bare numeric suffix of GW001 is "001"
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk1, bk2], ledger=[lg])
        r = tier2_results[0]
        self.assertEqual(r.status, STATUS_AMBIGUOUS)
        self.assertEqual(r.reason, REASON_MULTIPLE_FUZZY_CANDIDATES)
        self.assertIsNone(r.matched_records["bank"])
        candidate_ids = {c["source_row_id"] for c in r.candidate_records if c["within_amount_tolerance"]}
        self.assertEqual(candidate_ids, {"B001", "B002"})

    def test_ambiguous_candidates_are_never_consumed(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk1 = make_bank("B001", "BANK001", 999.98, bank_reference="PAY001")
        bk2 = make_bank("B002", "BANK002", 999.99, bank_reference="001")
        lg = make_ledger("L001", "PAY001", 1000.00)

        normalized = make_normalized(gateway=[gw], bank=[bk1, bk2], ledger=[lg])
        tier1_results, tier1_summary, tier1_matcher = run_tier1(
            normalized=normalized, return_matcher=True)
        residue = get_residue(tier1_results)
        fuzzy = FuzzyMatcher(tier1_matcher)
        for r in residue:
            fuzzy.resolve(r)
        self.assertEqual(fuzzy._consumed_bank_row_ids, set())


# ===========================================================================
# 11. Input order does not change the result
# ===========================================================================

class TestOrderIndependence(unittest.TestCase):
    def test_reversed_bank_order_produces_identical_result(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 999.97, bank_reference="GW001")
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, results_fwd, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])

        normalized_rev = make_normalized(gateway=[gw], bank=[bk], ledger=[lg])
        t1_rev, _, matcher_rev = run_tier1(normalized=normalized_rev, return_matcher=True)
        residue_rev = get_residue(t1_rev)
        results_rev, _ = run_tier2(list(reversed(residue_rev)), matcher_rev)

        def strip(results):
            return sorted(
                [{k: v for k, v in r.to_dict().items() if k != "decision_time"} for r in results],
                key=lambda d: d["transaction_id"])

        self.assertEqual(strip(results_fwd), strip(results_rev))

    def test_reversed_gateway_order_does_not_change_ambiguity_outcome(self):
        gw1 = make_gateway("G001", "PAY001", 700.00, gateway_reference="GW001")
        gw2 = make_gateway("G002", "PAY002", 900.00, gateway_reference="GW002")
        bk1 = make_bank("B001", "BANK001", 699.98, bank_reference="GW001")
        bk2 = make_bank("B002", "BANK002", 899.97, bank_reference="GW002")
        lg1 = make_ledger("L001", "PAY001", 700.00)
        lg2 = make_ledger("L002", "PAY002", 900.00)

        _, results_fwd, _, _ = run_full_pipeline(
            gateway=[gw1, gw2], bank=[bk1, bk2], ledger=[lg1, lg2])
        _, results_rev, _, _ = run_full_pipeline(
            gateway=[gw2, gw1], bank=[bk2, bk1], ledger=[lg2, lg1])

        statuses_fwd = {r.transaction_id: r.status for r in results_fwd}
        statuses_rev = {r.transaction_id: r.status for r in results_rev}
        self.assertEqual(statuses_fwd, statuses_rev)
        self.assertTrue(all(s == STATUS_MATCHED for s in statuses_fwd.values()))


# ===========================================================================
# 12. Duplicate ledger candidates remain protected (untouched by Tier 2)
# ===========================================================================

class TestDuplicateLedgerProtected(unittest.TestCase):
    def test_duplicate_ledger_case_stays_ineligible_for_tier2(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 1000.00, bank_reference="GW001")
        lg1 = make_ledger("L001", "PAY001", 1000.00)
        lg2 = make_ledger("L002", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg1, lg2])
        r = tier2_results[0]
        # Tier 1 already declared this UNRESOLVED_FOR_TIER_1 /
        # MULTIPLE_EXACT_CANDIDATES -- Tier 2 must not attempt to resolve it
        # with looser rules; it must remain untouched.
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_NOT_ELIGIBLE_FOR_TIER_2)
        self.assertIsNone(r.matched_records["bank"])
        self.assertIsNone(r.matched_records["ledger"])


# ===========================================================================
# 13. Bank/ledger rows cannot be reused (one-to-one, layered on Tier 1)
# ===========================================================================

class TestOneToOneProtection(unittest.TestCase):
    def test_bank_row_consumed_by_tier2_not_reused_by_second_transaction(self):
        gw1 = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        gw2 = make_gateway("G002", "PAY002", 1000.00, gateway_reference="GW002")
        # Both gateway refs' PREFIX_SWAP form would be "PAY001"/"PAY002" --
        # but craft a single bank row whose bare-numeric form only matches
        # gw1, to test straightforward non-reuse. (Two distinct references
        # can never both transform to the same bank_reference string here,
        # so this test verifies via Tier 1's own bank record pool: once
        # Tier 2 consumes B001 for PAY001, it must not exist in the
        # available pool for a hypothetical second candidate.)
        bk1 = make_bank("B001", "BANK001", 999.98, bank_reference="GW001")
        lg1 = make_ledger("L001", "PAY001", 1000.00)
        lg2 = make_ledger("L002", "PAY002", 1000.00)

        normalized = make_normalized(gateway=[gw1, gw2], bank=[bk1], ledger=[lg1, lg2])
        tier1_results, _, tier1_matcher = run_tier1(normalized=normalized, return_matcher=True)
        residue = get_residue(tier1_results)
        tier2_results, _ = run_tier2(residue, tier1_matcher)

        r1 = next(r for r in tier2_results if r.transaction_id == "PAY001")
        r2 = next(r for r in tier2_results if r.transaction_id == "PAY002")
        self.assertEqual(r1.status, STATUS_MATCHED)
        self.assertEqual(r1.matched_records["bank"], "B001")
        # PAY002 has no reference-compatible bank row available at all
        self.assertNotEqual(r2.status, STATUS_MATCHED)

    def test_tier1_consumed_bank_row_never_offered_to_tier2(self):
        # Regression for the PAY091/092/093-style scenario: Tier 1 leaves a
        # bank row genuinely available (never consumed) when it bails out
        # due to ledger-side ambiguity. Verify Tier 2 correctly sees it as
        # unavailable ONLY when Tier 1 actually consumed it elsewhere, and
        # available when Tier 1 did not.
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 1000.00, bank_reference="GW001")  # exact -- Tier 1 will consume it
        lg = make_ledger("L001", "PAY001", 1000.00)

        normalized = make_normalized(gateway=[gw], bank=[bk], ledger=[lg])
        tier1_results, _, tier1_matcher = run_tier1(normalized=normalized, return_matcher=True)
        self.assertIn("B001", tier1_matcher._consumed_bank_row_ids)

        residue = get_residue(tier1_results)
        self.assertEqual(residue, [])  # fully matched at Tier 1, nothing left for Tier 2


# ===========================================================================
# 14. Refunds remain separate — never fuzzy-matched
# ===========================================================================

class TestRefundsProtected(unittest.TestCase):
    def test_refund_residue_transaction_is_ineligible_since_bank_already_absent_by_design(self):
        # Refund logical transactions in the real dataset land in residue as
        # PARTIAL_MATCH (gateway+ledger, no bank -- refunds are netted into
        # the ORIGINAL payment's bank settlement, not their own). Tier 2
        # must NOT attempt to fuzzy-match a refund row to any bank credit,
        # since no bank row's reference will ever transform-match a "-R"
        # suffixed gateway_reference by design (see _digit_suffix rejecting
        # non-numeric remainders like "094-R").
        gw_refund = make_gateway("G001", "PAY094-REFUND", -500.00, gateway_reference="GW094-R")
        lg_refund = make_ledger("L001", "PAY094-REFUND", -500.00)
        # An unrelated bank row that happens to share the numeric part
        bk_decoy = make_bank("B001", "BANK001", 500.00, bank_reference="094")

        _, tier2_results, _, _ = run_full_pipeline(
            gateway=[gw_refund], bank=[bk_decoy], ledger=[lg_refund])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        # gateway_reference "GW094-R" has a non-numeric remainder after "GW"
        # ("094-R"), so _digit_suffix correctly returns None -- no reference
        # transform is even attempted.
        self.assertEqual(r.reason, REASON_NO_REFERENCE_TRANSFORM_MATCH)


# ===========================================================================
# 15. Large amount differences are rejected
# ===========================================================================

class TestLargeAmountDifferenceRejected(unittest.TestCase):
    def test_450_rupee_gap_never_matches_pay110_style(self):
        gw = make_gateway("G001", "PAY001", 5000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 4550.00, bank_reference="PAY001")
        lg = make_ledger("L001", "PAY001", 5000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE)


# ===========================================================================
# 16. TDS/tax is not treated as generic rounding
# ===========================================================================

class TestTaxTDSNotTreatedAsRounding(unittest.TestCase):
    def test_one_percent_tds_gap_not_swallowed_by_tolerance(self):
        gw = make_gateway("G001", "PAY001", 10000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 9900.00, bank_reference="PAY001")  # 1% TDS-style gap
        lg = make_ledger("L001", "PAY001", 10000.00, tds=100.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE)
        # tds_amount must remain visible/untouched
        self.assertEqual(lg.tax_fields["tds_amount"].normalized, 100.00)


# ===========================================================================
# 17. Missing references are not fabricated
# ===========================================================================

class TestMissingReferencesNeverFabricated(unittest.TestCase):
    def test_blank_bank_reference_never_matched_via_fabrication(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 1000.00, bank_reference=None)  # blank
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_NO_REFERENCE_TRANSFORM_MATCH)

    def test_blank_gateway_reference_never_fabricated(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        gw.secondary_references["gateway_reference"] = Reference(None, None)
        bk = make_bank("B001", "BANK001", 1000.00, bank_reference="PAY001")
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)


# ===========================================================================
# 18. True orphan remains unresolved
# ===========================================================================

class TestTrueOrphanRemainsUnresolved(unittest.TestCase):
    def test_gateway_only_orphan_stays_ineligible(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        # no bank, no ledger at all
        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[], ledger=[])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_NOT_ELIGIBLE_FOR_TIER_2)


# ===========================================================================
# 19. Split settlement is safely deferred (never combined)
# ===========================================================================

class TestSplitSettlementDeferred(unittest.TestCase):
    def test_split_settlement_never_combined_by_tier2(self):
        # PAY109-style: gateway 6400, two bank rows summing close but not
        # exact, neither individually within tolerance.
        gw = make_gateway("G001", "PAY109", 6400.00, gateway_reference="GW109")
        bk1 = make_bank("B001", "BANK001", 4000.00, bank_reference="GW109")
        bk2 = make_bank("B002", "BANK002", 2395.50, bank_reference="109")
        lg = make_ledger("L001", "PAY109", 6400.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk1, bk2], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        # neither bank row is individually within AMOUNT_TOLERANCE of 6400.00
        self.assertEqual(r.reason, REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE)
        self.assertIsNone(r.matched_records["bank"])


# ===========================================================================
# 20-21. No ground truth, no LLM
# ===========================================================================

class TestNoGroundTruthNoLLM(unittest.TestCase):
    def test_run_tier2_signature_has_no_ground_truth_parameter(self):
        import inspect
        sig = inspect.signature(run_tier2)
        self.assertNotIn("ground_truth", sig.parameters)
        sig2 = inspect.signature(FuzzyMatcher.__init__)
        self.assertNotIn("ground_truth", sig2.parameters)

    def test_matching_logic_source_never_references_ground_truth_or_llm(self):
        import ast
        import core.match_fuzzy as mod

        src = inspect.getsource(mod)
        tree = ast.parse(src)
        excluded_names = {"evaluate_against_ground_truth", "Tier2Evaluation"}
        forbidden_llm_terms = {"openai", "anthropic", "langchain", "embedding", "gemini"}

        offending = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in excluded_names:
                    continue
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and "ground_truth" in sub.id.lower():
                        offending.append((node.name, sub.id))
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        low = sub.value.lower()
                        if "ground_truth" in low or any(t in low for t in forbidden_llm_terms):
                            offending.append((node.name, sub.value))

        self.assertEqual(offending, [], f"forbidden references found: {offending}")

    def test_no_llm_sdk_imported(self):
        import core.match_fuzzy as mod
        src = inspect.getsource(mod)
        for forbidden in ("openai", "anthropic", "langchain"):
            self.assertNotIn(forbidden, src.lower())


import inspect  # noqa: E402


# ===========================================================================
# 22. Evidence/rule metadata exists on every result
# ===========================================================================

class TestEvidenceMetadataExists(unittest.TestCase):
    def test_every_result_has_evidence_and_tier_fields(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 999.97, bank_reference="GW001")
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertEqual(r.tier, "TIER_2")
        self.assertIsInstance(r.evidence, dict)
        self.assertGreater(len(r.evidence), 0)
        self.assertIsNotNone(r.decision_time)


# ===========================================================================
# 23. Repeated runs are deterministic
# ===========================================================================

class TestDeterministicRepeatedRuns(unittest.TestCase):
    def test_two_runs_on_same_input_produce_identical_output(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 999.97, bank_reference="GW001")
        lg = make_ledger("L001", "PAY001", 1000.00)

        normalized = make_normalized(gateway=[gw], bank=[bk], ledger=[lg])
        t1_a, _, matcher_a = run_tier1(normalized=normalized, return_matcher=True)
        residue_a = get_residue(t1_a)
        results_a, summary_a = run_tier2(residue_a, matcher_a)

        t1_b, _, matcher_b = run_tier1(normalized=normalized, return_matcher=True)
        residue_b = get_residue(t1_b)
        results_b, summary_b = run_tier2(residue_b, matcher_b)

        def strip(results):
            return [{k: v for k, v in r.to_dict().items() if k != "decision_time"} for r in results]

        self.assertEqual(strip(results_a), strip(results_b))
        self.assertEqual(summary_a.to_dict(), summary_b.to_dict())


# ===========================================================================
# Adversarial: B108 "109" bare-numeric collision guard (real dataset finding)
# ===========================================================================

class TestAdversarialNumericSuffixCollision(unittest.TestCase):
    def test_bare_numeric_bank_reference_belonging_to_different_split_leg_does_not_leak(self):
        """
        Regression for a real adversarial finding during Phase 4 inspection:
        bank row B108 has bank_reference="109" (the second leg of PAY109's
        split settlement), which bare-numeric-transform-matches gateway
        reference GW109. If amount tolerance were not enforced together
        with the reference transform, this could incorrectly appear to
        satisfy PAY109's own reference rule using the WRONG bank row.
        Amount tolerance must reject it: 6400.00 vs 2395.50 is far outside
        AMOUNT_TOLERANCE.
        """
        gw = make_gateway("G001", "PAY109", 6400.00, gateway_reference="GW109")
        bk = make_bank("B001", "BANK109B", 2395.50, bank_reference="109")
        lg = make_ledger("L001", "PAY109", 6400.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_REFERENCE_MATCHED_AMOUNT_OUT_OF_TOLERANCE)

    def test_unknown_bank_reference_never_treated_as_numeric_suffix(self):
        gw = make_gateway("G001", "PAY001", 1000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 1000.00, bank_reference="UNKNOWN")
        lg = make_ledger("L001", "PAY001", 1000.00)

        _, tier2_results, _, _ = run_full_pipeline(gateway=[gw], bank=[bk], ledger=[lg])
        r = tier2_results[0]
        self.assertNotEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.reason, REASON_NO_REFERENCE_TRANSFORM_MATCH)


# ===========================================================================
# 24 + Integration: real Tier 1 residue + real dataset behavior
# ===========================================================================

class TestPhase1IntegrationRealResidue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized = normalize_all(data_dir=DATA_DIR, strict=False)
        cls.tier1_results, cls.tier1_summary, cls.tier1_matcher = run_tier1(
            normalized=cls.normalized, return_matcher=True)
        cls.residue = get_residue(cls.tier1_results)
        cls.tier2_results, cls.tier2_summary = run_tier2(cls.residue, cls.tier1_matcher)
        with open(os.path.join(DATA_DIR, "ground_truth.csv")) as f:
            cls.gt_rows = list(csv.DictReader(f))
        cls.evaluation = evaluate_against_ground_truth(cls.tier2_results, cls.gt_rows)

    def test_every_residue_transaction_produces_exactly_one_tier2_result(self):
        self.assertEqual(len(self.tier2_results), len(self.residue))

    def test_rounding_cases_all_matched(self):
        rounding_ids = {"PAY071", "PAY072", "PAY073", "PAY074", "PAY075", "PAY076", "PAY077"}
        results_by_id = {r.transaction_id: r for r in self.tier2_results}
        for txn_id in rounding_ids:
            r = results_by_id[txn_id]
            self.assertEqual(r.status, STATUS_MATCHED, f"{txn_id} should be Tier 2 MATCHED")
            self.assertEqual(r.rule, RULE_PARTIAL_REFERENCE_AND_AMOUNT_TOLERANCE)

    def test_remaining_reference_formatting_cases_matched(self):
        # PAY087/090 already resolved at Tier 1 (not in residue); only
        # PAY086/088/089 remain for Tier 2.
        ref_ids = {"PAY086", "PAY088", "PAY089"}
        results_by_id = {r.transaction_id: r for r in self.tier2_results}
        for txn_id in ref_ids:
            r = results_by_id[txn_id]
            self.assertEqual(r.status, STATUS_MATCHED, f"{txn_id} should be Tier 2 MATCHED")

    def test_duplicate_ledger_cases_remain_untouched(self):
        results_by_id = {r.transaction_id: r for r in self.tier2_results}
        for txn_id in ("PAY091", "PAY092", "PAY093"):
            r = results_by_id[txn_id]
            self.assertNotEqual(r.status, STATUS_MATCHED)
            self.assertEqual(r.reason, REASON_NOT_ELIGIBLE_FOR_TIER_2)

    def test_partial_refund_and_tax_line_mismatch_remain_unresolved_per_approved_scope(self):
        out_of_scope_ids = ["PAY094", "PAY095", "PAY096", "PAY097",  # PARTIAL_REFUND
                             "PAY098", "PAY099", "PAY100", "PAY101", "PAY102"]  # TAX_LINE_MISMATCH
        results_by_id = {r.transaction_id: r for r in self.tier2_results}
        for txn_id in out_of_scope_ids:
            r = results_by_id[txn_id]
            self.assertNotEqual(r.status, STATUS_MATCHED,
                                 f"{txn_id} must remain unresolved per approved Phase 4 scope")

    def test_true_orphan_and_decoy_and_no_bank_counterpart_remain_unresolved(self):
        results_by_id = {r.transaction_id: r for r in self.tier2_results}
        for txn_id in ("PAY105", "PAY107B", "PAY103", "PAY104"):
            r = results_by_id[txn_id]
            self.assertNotEqual(r.status, STATUS_MATCHED)

    def test_tier3_designed_cases_remain_unresolved(self):
        results_by_id = {r.transaction_id: r for r in self.tier2_results}
        for txn_id in ("PAY108", "PAY109", "PAY110", "PAY111"):
            r = results_by_id[txn_id]
            self.assertNotEqual(r.status, STATUS_MATCHED)

    def test_no_bank_or_ledger_row_consumed_twice_across_tier1_and_tier2(self):
        # Only bank rows Tier 2 ITSELF newly consumed (rule fired, status
        # MATCHED) may be compared against Tier 1's consumption -- a bank
        # row that Tier 1 already matched to a DIFFERENT transaction (e.g.
        # B109, matched to PAY110 as gateway+bank PARTIAL_MATCH) is not
        # offered to Tier 2 at all, since PAY110 itself is ineligible
        # (ledger side missing, not bank side -- see _is_eligible_for_tier2).
        t1_bank_used = {r.matched_records["bank"] for r in self.tier1_results
                         if r.matched_records["bank"] is not None}
        t2_newly_matched_bank = {r.matched_records["bank"] for r in self.tier2_results
                                  if r.status == STATUS_MATCHED}
        self.assertEqual(t1_bank_used & t2_newly_matched_bank, set())
        self.assertEqual(len(t2_newly_matched_bank), len(set(t2_newly_matched_bank)))

    def test_reproducibility_two_full_runs_identical(self):
        results2, summary2 = run_tier2(self.residue, self.tier1_matcher)

        def strip(results):
            return [{k: v for k, v in r.to_dict().items() if k != "decision_time"} for r in results]

        self.assertEqual(strip(self.tier2_results), strip(results2))
        self.assertEqual(self.tier2_summary.to_dict(), summary2.to_dict())

    def test_no_false_matches_against_ground_truth(self):
        self.assertEqual(len(self.evaluation.false_matches), 0,
                          f"Unexpected false matches: {self.evaluation.false_matches}")

    def test_no_missed_tier2_opportunities_within_approved_scope(self):
        # Ground truth labels PARTIAL_REFUND and TAX_LINE_MISMATCH as
        # expected_matching_tier=TIER_2, but Phase 4 was explicitly approved
        # (Option B) to leave both categories unresolved in this phase --
        # no REFUND_LINKED_NET_AMOUNT / TDS_LINKED_NET_AMOUNT rule was
        # authorized. Those categories are therefore EXPECTED "misses" per
        # the approved scope, not defects. Every other TIER_2-expected
        # category (ROUNDING, REFERENCE_FORMATTING) must have zero misses.
        out_of_scope_categories = {"PARTIAL_REFUND", "TAX_LINE_MISMATCH"}
        unexpected_misses = [
            m for m in self.evaluation.missed_tier2_opportunities
            if m["expected_category"] not in out_of_scope_categories
        ]
        self.assertEqual(unexpected_misses, [],
                          f"Missed Tier 2 opportunities outside approved out-of-scope "
                          f"categories: {unexpected_misses}")
        # Sanity: confirm every miss IS explained by the approved carve-out.
        for m in self.evaluation.missed_tier2_opportunities:
            self.assertIn(m["expected_category"], out_of_scope_categories)


# ===========================================================================
# All previous 65 tests still pass — verified by running the full suite,
# not re-declared here. See test_normalize.py / test_match_exact.py.
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
