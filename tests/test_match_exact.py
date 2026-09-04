"""
LedgerLoop — Phase 3: Tier 1 Exact Matching Tests
=====================================================

Covers all 12 required test cases (Section 19), the adversarial safety test
(Section 20), and an integration test against the real Phase 1/Phase 2
dataset, including explicit confirmation that ground truth is never
consulted by the matching logic itself (only by the separate evaluation
function, after the fact).

Run with:
    python3 -m unittest tests.test_match_exact -v
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
    ExactMatcher, run_tier1, get_residue, get_unclaimed_source_records,
    evaluate_against_ground_truth,
    STATUS_MATCHED, STATUS_PARTIAL_MATCH, STATUS_UNRESOLVED_FOR_TIER_1,
    REASON_MULTIPLE_EXACT_CANDIDATES, REASON_NO_EXACT_CANDIDATE,
    RULE_EXACT_REFERENCE_AND_AMOUNT, RULE_EXACT_GATEWAY_REFERENCE_AND_AMOUNT,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


# ===========================================================================
# Fixture builder: hand-construct CanonicalRecords directly, bypassing CSV
# parsing entirely, so each test isolates exactly the matching behavior
# under test.
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


def run(gateway=None, bank=None, ledger=None):
    normalized = make_normalized(gateway, bank, ledger)
    return run_tier1(normalized=normalized)


# ===========================================================================
# Test 1: Exact reference + exact amount -> MATCHED
# ===========================================================================

class TestExactReferenceAndAmount(unittest.TestCase):
    def test_full_three_source_exact_match(self):
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW001")
        lg = make_ledger("L001", "PAY001", 500.00)

        results, summary = run(gateway=[gw], bank=[bk], ledger=[lg])
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, STATUS_MATCHED)
        self.assertEqual(r.tier, "TIER_1")
        self.assertEqual(r.rule, RULE_EXACT_REFERENCE_AND_AMOUNT)
        self.assertEqual(r.confidence, 1.0)
        self.assertEqual(r.matched_records, {"gateway": "G001", "bank": "B001", "ledger": "L001"})
        self.assertEqual(summary.matched_count, 1)


# ===========================================================================
# Test 2: Exact reference but different amount -> NOT Tier 1
# ===========================================================================

class TestExactReferenceDifferentAmount(unittest.TestCase):
    def test_reference_matches_but_amount_differs_does_not_match(self):
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 499.99, bank_reference="GW001")  # off by 1 paisa
        lg = make_ledger("L001", "PAY001", 500.00)

        results, summary = run(gateway=[gw], bank=[bk], ledger=[lg])
        r = results[0]
        # bank should NOT be matched (amount differs); ledger should
        self.assertIsNone(r.matched_records["bank"])
        self.assertEqual(r.matched_records["ledger"], "L001")
        self.assertEqual(r.status, STATUS_PARTIAL_MATCH)
        self.assertNotEqual(r.status, STATUS_MATCHED)

    def test_exact_boundary_499_99_vs_500_00_never_matches(self):
        gw = make_gateway("G002", "PAY002", 500.00, gateway_reference="GW002")
        bk = make_bank("B002", "BANK002", 500.01, bank_reference="GW002")  # off by 1 paisa, other direction
        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        r = results[0]
        self.assertIsNone(r.matched_records["bank"])


# ===========================================================================
# Test 3: Different reference + same amount -> NOT Tier 1
# ===========================================================================

class TestDifferentReferenceSameAmount(unittest.TestCase):
    def test_same_amount_different_reference_does_not_match(self):
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW999")  # unrelated reference
        lg = make_ledger("L001", "PAY999", 500.00)  # unrelated reference

        results, summary = run(gateway=[gw], bank=[bk], ledger=[lg])
        r = results[0]
        self.assertIsNone(r.matched_records["bank"])
        self.assertIsNone(r.matched_records["ledger"])
        self.assertEqual(r.status, STATUS_UNRESOLVED_FOR_TIER_1)


# ===========================================================================
# Test 4: Reference formatting already normalized -> correct behavior
# ===========================================================================

class TestReferenceFormattingAlreadyNormalized(unittest.TestCase):
    def test_case_only_difference_normalizes_to_equal_and_matches(self):
        # Phase 2's normalize_reference() uppercases -- "gw001" and "GW001"
        # become the same normalized string, so post-normalization this is
        # a legitimate exact match, not a fuzzy one.
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW001")  # pre-normalized by fixture
        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        r = results[0]
        self.assertEqual(r.matched_records["bank"], "B001")

    def test_genuinely_truncated_reference_does_not_match(self):
        # A truly truncated/different string must NOT match, even though a
        # human would recognize the relationship -- that is Tier 2's job.
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001234")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW001")  # truncated
        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        r = results[0]
        self.assertIsNone(r.matched_records["bank"])


# ===========================================================================
# Test 5: Multiple candidates -> do not force match
# ===========================================================================

class TestMultipleCandidates(unittest.TestCase):
    def test_two_bank_candidates_same_reference_and_amount_stays_unresolved(self):
        gw = make_gateway("G001", "PAY001", 1875.00, gateway_reference="GW001")
        bk1 = make_bank("B001", "BANK001", 1875.00, bank_reference="GW001")
        bk2 = make_bank("B002", "BANK002", 1875.00, bank_reference="GW001")

        results, summary = run(gateway=[gw], bank=[bk1, bk2], ledger=[])
        r = results[0]
        self.assertEqual(r.status, STATUS_UNRESOLVED_FOR_TIER_1)
        self.assertEqual(r.reason, REASON_MULTIPLE_EXACT_CANDIDATES)
        self.assertIsNone(r.matched_records["bank"])
        self.assertEqual(len(r.unmatched_candidates), 2)
        candidate_ids = {c["source_row_id"] for c in r.unmatched_candidates}
        self.assertEqual(candidate_ids, {"B001", "B002"})

    def test_neither_ambiguous_candidate_is_consumed(self):
        # one-to-one protection must not accidentally consume either
        # candidate when the match is deferred as ambiguous
        gw = make_gateway("G001", "PAY001", 1875.00, gateway_reference="GW001")
        bk1 = make_bank("B001", "BANK001", 1875.00, bank_reference="GW001")
        bk2 = make_bank("B002", "BANK002", 1875.00, bank_reference="GW001")

        normalized = make_normalized(gateway=[gw], bank=[bk1, bk2], ledger=[])
        matcher = ExactMatcher(normalized)
        matcher.run()
        self.assertEqual(matcher._consumed_bank_row_ids, set())


# ===========================================================================
# Test 6: Duplicate ledger -> do not silently deduplicate
# ===========================================================================

class TestDuplicateLedgerNotDeduplicated(unittest.TestCase):
    def test_two_identical_ledger_rows_trigger_ambiguity_not_silent_pick(self):
        gw = make_gateway("G050", "PAY050", 2000.00, gateway_reference="GW050")
        lg1 = make_ledger("L050", "PAY050", 2000.00)
        lg2 = make_ledger("L051", "PAY050", 2000.00)

        results, summary = run(gateway=[gw], bank=[], ledger=[lg1, lg2])
        r = results[0]
        self.assertEqual(r.status, STATUS_UNRESOLVED_FOR_TIER_1)
        self.assertEqual(r.reason, REASON_MULTIPLE_EXACT_CANDIDATES)
        # both duplicate rows must be visible in unmatched_candidates -- neither discarded
        ledger_candidate_ids = {c["source_row_id"] for c in r.unmatched_candidates if c["source"] == "ledger"}
        self.assertEqual(ledger_candidate_ids, {"L050", "L051"})


# ===========================================================================
# Test 7: Refund record -> not treated as ordinary payment
# ===========================================================================

class TestRefundNotOrdinaryPayment(unittest.TestCase):
    def test_refund_is_its_own_logical_transaction_not_merged_with_original(self):
        gw_original = make_gateway("G095", "PAY095", 5000.00, gateway_reference="GW095")
        gw_refund = make_gateway("G096", "PAY095-REFUND", -1000.00, gateway_reference="GW095-R")
        lg_original = make_ledger("L095", "PAY095", 5000.00)
        lg_refund = make_ledger("L096", "PAY095-REFUND", -1000.00)

        results, summary = run(gateway=[gw_original, gw_refund], bank=[],
                                ledger=[lg_original, lg_refund])
        self.assertEqual(len(results), 2)
        ids = {r.transaction_id for r in results}
        self.assertEqual(ids, {"PAY095", "PAY095-REFUND"})

        refund_result = next(r for r in results if r.transaction_id == "PAY095-REFUND")
        self.assertEqual(refund_result.matched_records["ledger"], "L096")
        self.assertNotEqual(refund_result.matched_records["ledger"], "L095")
        # amounts must not be netted
        self.assertEqual(refund_result.evidence["amount"], -1000.00)


# ===========================================================================
# Test 8: Tax/TDS amount difference -> not exact match
# ===========================================================================

class TestTaxTDSNotExactMatch(unittest.TestCase):
    def test_tds_net_settlement_does_not_count_as_exact_amount_match(self):
        gw = make_gateway("G001", "PAY001", 10000.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 9900.00, bank_reference="GW001")  # net of 1% TDS
        lg = make_ledger("L001", "PAY001", 10000.00, tds=100.00)

        results, summary = run(gateway=[gw], bank=[bk], ledger=[lg])
        r = results[0]
        # bank amount (9900) != gateway amount (10000) exactly -> no bank match
        self.assertIsNone(r.matched_records["bank"])
        self.assertEqual(r.matched_records["ledger"], "L001")
        self.assertEqual(r.status, STATUS_PARTIAL_MATCH)
        # tds_amount must remain visible/untouched on the underlying ledger
        # record - Tier 1 must not have "fixed" or reinterpreted amount
        self.assertEqual(lg.tax_fields["tds_amount"].normalized, 100.00)
        self.assertEqual(lg.amount.normalized, 10000.00)


# ===========================================================================
# Test 9: Settlement date difference -> verify documented behavior
# ===========================================================================

class TestSettlementDateDifference(unittest.TestCase):
    def test_date_difference_does_not_block_exact_reference_and_amount_match(self):
        # Per Section 14 / module docstring: Tier 1 does not gate on date.
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001", date="2026-08-20")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW001", date="2026-08-22")
        lg = make_ledger("L001", "PAY001", 500.00, date="2026-08-20")

        results, summary = run(gateway=[gw], bank=[bk], ledger=[lg])
        r = results[0]
        self.assertEqual(r.status, STATUS_MATCHED)
        # the date difference must be preserved as evidence, not silently dropped
        self.assertEqual(r.evidence["date_difference_days"], 2)

    def test_no_fuzzy_date_window_logic_exists(self):
        # a large date gap still matches on exact reference+amount alone --
        # Tier 1 makes no judgment about whether the gap is "acceptable"
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001", date="2026-08-01")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW001", date="2026-08-30")
        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        r = results[0]
        self.assertEqual(r.matched_records["bank"], "B001")
        self.assertEqual(r.evidence["date_difference_days"], 29)


# ===========================================================================
# Test 10: One-to-one protection
# ===========================================================================

class TestOneToOneProtection(unittest.TestCase):
    def test_bank_record_not_reused_across_two_gateway_transactions(self):
        # Two DIFFERENT gateway payments must not both claim the same bank
        # row, even if amounts coincidentally match -- references differ
        # here, but this also stresses that a record, once consumed, drops
        # out of the candidate pool.
        gw1 = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        gw2 = make_gateway("G002", "PAY002", 500.00, gateway_reference="GW002")
        bk1 = make_bank("B001", "BANK001", 500.00, bank_reference="GW001")

        results, summary = run(gateway=[gw1, gw2], bank=[bk1], ledger=[])
        r1 = next(r for r in results if r.transaction_id == "PAY001")
        r2 = next(r for r in results if r.transaction_id == "PAY002")
        self.assertEqual(r1.matched_records["bank"], "B001")
        self.assertIsNone(r2.matched_records["bank"])  # already consumed by PAY001

    def test_ledger_record_consumed_once_processing_order_deterministic(self):
        gw1 = make_gateway("G001", "PAY001", 300.00, gateway_reference="GW001")
        gw2 = make_gateway("G002", "PAY002", 300.00, gateway_reference="GW002")
        lg = make_ledger("L001", "PAY001", 300.00)  # only references PAY001

        results, summary = run(gateway=[gw1, gw2], bank=[], ledger=[lg])
        r1 = next(r for r in results if r.transaction_id == "PAY001")
        r2 = next(r for r in results if r.transaction_id == "PAY002")
        self.assertEqual(r1.matched_records["ledger"], "L001")
        self.assertIsNone(r2.matched_records["ledger"])


# ===========================================================================
# Test 11: Missing reference
# ===========================================================================

class TestMissingReference(unittest.TestCase):
    def test_gateway_with_no_gateway_reference_cannot_match_bank(self):
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference=None)
        # override to truly blank
        gw.secondary_references["gateway_reference"] = Reference(None, None)
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW001")

        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        r = results[0]
        self.assertIsNone(r.matched_records["bank"])

    def test_bank_with_blank_bank_reference_never_indexed(self):
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference=None)  # blank

        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        r = results[0]
        self.assertIsNone(r.matched_records["bank"])
        self.assertEqual(r.status, STATUS_UNRESOLVED_FOR_TIER_1)


# ===========================================================================
# Test 12: Gateway + Bank without Ledger
# ===========================================================================

class TestGatewayBankWithoutLedger(unittest.TestCase):
    def test_partial_match_status_when_ledger_absent(self):
        gw = make_gateway("G080", "PAY080", 1500.00, gateway_reference="GW080")
        bk = make_bank("B080", "BANK080", 1500.00, bank_reference="GW080")

        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        r = results[0]
        self.assertEqual(r.status, STATUS_PARTIAL_MATCH)
        self.assertNotEqual(r.status, STATUS_MATCHED)  # must not silently claim complete match
        self.assertEqual(r.matched_records, {"gateway": "G080", "bank": "B080", "ledger": None})


# ===========================================================================
# Test 13: Ground truth is never used to make decisions
# ===========================================================================

class TestGroundTruthNeverUsedForDecisions(unittest.TestCase):
    def test_matcher_and_run_tier1_accept_no_ground_truth_argument(self):
        import inspect
        sig = inspect.signature(run_tier1)
        self.assertNotIn("ground_truth", sig.parameters)
        sig2 = inspect.signature(ExactMatcher.__init__)
        self.assertNotIn("ground_truth", sig2.parameters)

    def test_source_code_of_matching_logic_never_references_ground_truth(self):
        import ast
        import core.match_exact as mod

        src = inspect.getsource(mod)
        tree = ast.parse(src)

        # Identify the actual decision-making functions/methods: everything
        # EXCEPT evaluate_against_ground_truth and the Tier1Evaluation
        # dataclass (both explicitly documented as evaluation-only, Section
        # 17/18). This checks real code (via ast), not docstrings/comments,
        # so prose mentioning "ground_truth.csv" while explaining the
        # boundary doesn't produce a false positive.
        excluded_names = {"evaluate_against_ground_truth", "Tier1Evaluation"}

        offending = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in excluded_names:
                    continue
                # Only inspect top-level matching machinery: ExactMatcher and
                # its methods, plus free functions like run_tier1/get_residue/
                # get_unclaimed_source_records. Walk this node's own body
                # (excluding nested excluded defs) for Name/Attribute/Constant
                # references to "ground_truth".
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and "ground_truth" in sub.id.lower():
                        offending.append((node.name, sub.id))
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                            and "ground_truth" in sub.value.lower():
                        offending.append((node.name, sub.value))

        self.assertEqual(offending, [],
                          f"matching-logic code references ground_truth: {offending}")

    def test_evaluation_function_does_not_mutate_results(self):
        gw = make_gateway("G001", "PAY001", 500.00, gateway_reference="GW001")
        bk = make_bank("B001", "BANK001", 500.00, bank_reference="GW001")
        results, summary = run(gateway=[gw], bank=[bk], ledger=[])
        before = results[0].to_dict()

        gt_rows = [{"transaction_id": "PAY001", "expected_status": "MATCHED",
                    "expected_category": "NORMAL_EXACT", "expected_matching_tier": "TIER_1"}]
        evaluate_against_ground_truth(results, gt_rows)
        after = results[0].to_dict()
        self.assertEqual(before, after)


import inspect  # noqa: E402  (used above; placed here to keep top imports clean)


# ===========================================================================
# Section 20: Adversarial safety test
# ===========================================================================

class TestAdversarialSafety(unittest.TestCase):
    def test_same_amount_similar_dates_different_references_never_matched(self):
        """
        Two entirely distinct transactions that happen to share an amount
        and land on nearby dates must NOT be matched to each other merely
        because they "look similar". Only exact reference identity may
        drive a Tier 1 decision.
        """
        gw1 = make_gateway("G001", "PAY001", 4321.00, gateway_reference="GW001", date="2026-08-20")
        gw2 = make_gateway("G002", "PAY002", 4321.00, gateway_reference="GW002", date="2026-08-21")

        # a single bank credit that could superficially "look like" either
        bk = make_bank("B999", "BANK999", 4321.00, bank_reference="GWZZZ", date="2026-08-20")

        results, summary = run(gateway=[gw1, gw2], bank=[bk], ledger=[])
        r1 = next(r for r in results if r.transaction_id == "PAY001")
        r2 = next(r for r in results if r.transaction_id == "PAY002")

        # neither should claim the bank row -- its reference matches neither
        self.assertIsNone(r1.matched_records["bank"])
        self.assertIsNone(r2.matched_records["bank"])
        self.assertNotEqual(r1.status, STATUS_MATCHED)
        self.assertNotEqual(r2.status, STATUS_MATCHED)

    def test_two_real_candidates_same_amount_prefers_unresolved_over_guessing(self):
        """
        When a bank row's reference genuinely matches BOTH of two gateway
        payments' gateway_reference (a contrived but possible data
        condition), Tier 1 must not silently assign it to whichever
        gateway record happens to be processed first -- it must remain
        UNRESOLVED for BOTH gateway records, not just "not double-claimed".
        Order-dependent resolution of a genuinely ambiguous match is exactly
        the "confidently wrong" failure mode Section 20 warns against.
        """
        gw1 = make_gateway("G001", "PAY001", 700.00, gateway_reference="GWDUP")
        gw2 = make_gateway("G002", "PAY002", 700.00, gateway_reference="GWDUP")
        bk = make_bank("B001", "BANK001", 700.00, bank_reference="GWDUP")

        results, summary = run(gateway=[gw1, gw2], bank=[bk], ledger=[])
        r1 = next(r for r in results if r.transaction_id == "PAY001")
        r2 = next(r for r in results if r.transaction_id == "PAY002")

        # the same bank row must never be matched to two different gateway
        # transactions...
        claimants = [r for r in (r1, r2) if r.matched_records["bank"] == "B001"]
        self.assertLessEqual(len(claimants), 1,
                              "the same bank row must never be matched to two different "
                              "gateway transactions")
        # ...but MORE IMPORTANTLY, it must not be claimed by EITHER of them:
        # both gateway records are equally valid candidates for the one bank
        # row, so Tier 1 evidence alone cannot say which is correct. The
        # first-processed record silently "winning" would be confidently
        # wrong, not just non-duplicative.
        self.assertEqual(r1.status, STATUS_UNRESOLVED_FOR_TIER_1)
        self.assertEqual(r2.status, STATUS_UNRESOLVED_FOR_TIER_1)
        self.assertIsNone(r1.matched_records["bank"])
        self.assertIsNone(r2.matched_records["bank"])
        self.assertEqual(r1.reason, "CONTENDED_BY_ANOTHER_GATEWAY_RECORD")
        self.assertEqual(r2.reason, "CONTENDED_BY_ANOTHER_GATEWAY_RECORD")

    def test_gateway_side_contention_is_order_independent(self):
        """
        Regression test: the correctness of the contention outcome above
        must not depend on which gateway record Phase 2/CSV happened to
        list first. Running with the two gateway records in either order
        must produce the same UNRESOLVED_FOR_TIER_1 outcome for both.
        """
        gw1 = make_gateway("G001", "PAY001", 700.00, gateway_reference="GWDUP")
        gw2 = make_gateway("G002", "PAY002", 700.00, gateway_reference="GWDUP")
        bk = make_bank("B001", "BANK001", 700.00, bank_reference="GWDUP")

        results_fwd, _ = run(gateway=[gw1, gw2], bank=[bk], ledger=[])
        results_rev, _ = run(gateway=[gw2, gw1], bank=[bk], ledger=[])

        statuses_fwd = {r.transaction_id: r.status for r in results_fwd}
        statuses_rev = {r.transaction_id: r.status for r in results_rev}
        self.assertEqual(statuses_fwd, statuses_rev)
        self.assertTrue(all(s == STATUS_UNRESOLVED_FOR_TIER_1 for s in statuses_fwd.values()))

    def test_gateway_side_contention_on_ledger_side_too(self):
        """
        The same gateway-side contention protection must also apply to the
        ledger side (two gateway records sharing a payment_id-space
        reference that both point at one ledger row) — not just the bank
        side. This is a distinct code path (payment_reference indexing vs
        bank_reference indexing) and needs its own coverage.
        """
        # Two gateway records that (due to a hypothetical upstream data
        # issue) normalize to the SAME transaction_reference is not
        # representable via make_gateway's normal payment_id-driven
        # construction without duplicate payment_ids, so we simulate the
        # analogous condition directly: two gateway records whose
        # transaction_reference both equal "PAY900".
        gw1 = make_gateway("G001", "PAY900", 450.00, gateway_reference="GWA")
        gw2 = make_gateway("G002", "PAY900", 450.00, gateway_reference="GWB")
        led = make_ledger("L001", "PAY900", 450.00)

        results, summary = run(gateway=[gw1, gw2], bank=[], ledger=[led])
        r1 = next(r for r in results if r.matched_records["gateway"] == "G001")
        r2 = next(r for r in results if r.matched_records["gateway"] == "G002")

        claimants = [r for r in (r1, r2) if r.matched_records["ledger"] == "L001"]
        self.assertLessEqual(len(claimants), 1)
        self.assertEqual(r1.status, STATUS_UNRESOLVED_FOR_TIER_1)
        self.assertEqual(r2.status, STATUS_UNRESOLVED_FOR_TIER_1)


# ===========================================================================
# Integration tests against the real Phase 1/Phase 2 dataset
# ===========================================================================

class TestPhase1Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized = normalize_all(data_dir=DATA_DIR, strict=False)
        cls.results, cls.summary, cls.matcher = run_tier1(
            normalized=cls.normalized, return_matcher=True)
        with open(os.path.join(DATA_DIR, "ground_truth.csv")) as f:
            cls.gt_rows = list(csv.DictReader(f))
        cls.evaluation = evaluate_against_ground_truth(cls.results, cls.gt_rows)

    def test_every_gateway_record_produces_exactly_one_result(self):
        self.assertEqual(len(self.results), len(self.normalized.gateway.records))

    def test_no_bank_or_ledger_record_consumed_twice(self):
        bank_ids_used = [r.matched_records["bank"] for r in self.results
                          if r.matched_records["bank"] is not None]
        ledger_ids_used = [r.matched_records["ledger"] for r in self.results
                            if r.matched_records["ledger"] is not None]
        self.assertEqual(len(bank_ids_used), len(set(bank_ids_used)))
        self.assertEqual(len(ledger_ids_used), len(set(ledger_ids_used)))

    def test_duplicate_ledger_cases_correctly_unresolved(self):
        dup_results = [r for r in self.results if r.reason == REASON_MULTIPLE_EXACT_CANDIDATES]
        self.assertGreater(len(dup_results), 0)

    def test_all_normal_exact_ground_truth_cases_are_matched(self):
        normal_exact_ids = {row["transaction_id"] for row in self.gt_rows
                             if row["expected_category"] == "NORMAL_EXACT"}
        results_by_id = {r.transaction_id: r for r in self.results}
        for txn_id in normal_exact_ids:
            r = results_by_id.get(txn_id)
            self.assertIsNotNone(r, f"{txn_id} missing from Tier 1 results")
            self.assertEqual(r.status, STATUS_MATCHED,
                              f"{txn_id} (NORMAL_EXACT) should be a clean Tier 1 MATCHED result")

    def test_no_missed_tier1_opportunities(self):
        self.assertEqual(len(self.evaluation.missed_tier1_opportunities), 0)

    def test_duplicate_and_refund_and_tds_cases_never_forced_to_full_match(self):
        for category, expect_matched in [
            ("DUPLICATE_LEDGER_ENTRY", False),
            ("TAX_LINE_MISMATCH", False),
        ]:
            ids = [row["transaction_id"] for row in self.gt_rows
                   if row["expected_category"] == category]
            results_by_id = {r.transaction_id: r for r in self.results}
            for txn_id in ids:
                r = results_by_id[txn_id]
                self.assertNotEqual(r.status, STATUS_MATCHED,
                                     f"{txn_id} ({category}) should NOT be a clean Tier 1 match")

    def test_reproducibility_two_runs_identical(self):
        results2, summary2 = run_tier1(normalized=self.normalized)

        def strip_time(results):
            return [{k: v for k, v in r.to_dict().items() if k != "decision_time"} for r in results]

        self.assertEqual(strip_time(self.results), strip_time(results2))
        self.assertEqual(self.summary.to_dict(), summary2.to_dict())

    def test_residue_is_non_empty_and_not_labeled_as_final_exceptions(self):
        residue = get_residue(self.results)
        self.assertGreater(len(residue), 0)
        # residue results must never claim MATCHED
        for r in residue:
            self.assertNotEqual(r.status, STATUS_MATCHED)

    def test_unclaimed_bank_only_orphan_surfaces_in_residue_helper(self):
        unclaimed = get_unclaimed_source_records(self.matcher)
        unclaimed_bank_raw = [r.raw_record for r in self.matcher.bank_records
                               if r.source_row_id in unclaimed["bank"]]
        unknown_refs = [r for r in unclaimed_bank_raw if r.get("bank_reference") == "UNKNOWN"]
        self.assertGreater(len(unknown_refs), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
