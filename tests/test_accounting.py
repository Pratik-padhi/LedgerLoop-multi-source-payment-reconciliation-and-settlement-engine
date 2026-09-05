"""
Focused deterministic tests for the accounting settlement layer (core/accounting.py).

These tests verify the reusable, Python-authoritative settlement arithmetic.
No LLM calls are involved. No live data is required — all fixtures are
static, self-contained, and do not depend on specific transaction IDs.
"""

import unittest
from decimal import Decimal

from core.accounting import (
    # Core primitives
    gst_decomposition,
    compute_expected_net,
    compute_settlement,
    build_settlement_from_ledger,
    # Statuses and reasons
    STATUS_EXACT,
    STATUS_EXPLAINED,
    STATUS_UNEXPLAINED,
    REASON_FULLY_EXPLAINED,
    REASON_UNEXPLAINED_VARIANCE,
    REASON_NO_ACCOUNTING_EVIDENCE,
    REASON_CONTRADICTORY_EVIDENCE,
    REASON_REFUND_EXCEEDS_GROSS,
    # GST consistency
    GST_CONSISTENT,
    GST_INCONSISTENT,
    GST_NO_EVIDENCE,
    # Exceptions
    AccountingValidationError,
    # Data class
    SettlementBreakdown,
)


class TestGstDecomposition(unittest.TestCase):
    """GST corroboration: taxable + gst == target (bank)."""

    def test_consistent(self):
        cons, ev = gst_decomposition(10000, 1800, 11800)
        self.assertEqual(cons, GST_CONSISTENT)
        self.assertEqual(ev["relationship"], "taxable + gst = gross")
        self.assertEqual(ev["implied_gross"], 11800.0)
        self.assertEqual(ev["reported_gross"], 11800.0)

    def test_inconsistent(self):
        cons, ev = gst_decomposition(10000, 1800, 12000)
        self.assertEqual(cons, GST_INCONSISTENT)
        self.assertEqual(ev["implied_gross"], 11800.0)
        self.assertEqual(ev["reported_gross"], 12000.0)

    def test_no_evidence(self):
        cons, ev = gst_decomposition(10000, 0, 10000)
        self.assertEqual(cons, GST_NO_EVIDENCE)
        self.assertEqual(ev["gst_evidence"], GST_NO_EVIDENCE)


class TestComputeExpectedNet(unittest.TestCase):
    """The one deterministic settlement path:
    expected = gross + gst - tds - mdr - mdr_gst - fee - refund
    """

    def test_gst_only(self):
        # gateway pre-GST 10000, GST 1800 -> expected bank 11800
        self.assertEqual(compute_expected_net(10000, gst=1800), Decimal("11800"))

    def test_tds_only(self):
        self.assertEqual(compute_expected_net(50000, tds=500), Decimal("49500"))

    def test_mdr_fee_only(self):
        # gross 10000 - mdr 150 - mdr_gst 27 - fee 0 = 9823
        self.assertEqual(compute_expected_net(10000, mdr=150, mdr_gst=27), Decimal("9823"))

    def test_refund_only(self):
        self.assertEqual(compute_expected_net(1000, refund=300), Decimal("700"))

    def test_combined(self):
        # 10000 + 1800 - 500 - 150 - 27 - 300 = 10823
        self.assertEqual(
            compute_expected_net(10000, gst=1800, tds=500, mdr=150, mdr_gst=27, refund=300),
            Decimal("10823"),
        )

    def test_zero_amounts(self):
        self.assertEqual(compute_expected_net(0), Decimal("0"))
        self.assertEqual(compute_expected_net(100), Decimal("100"))

    def test_rejects_nan(self):
        with self.assertRaises(AccountingValidationError):
            compute_expected_net(float("nan"))
        with self.assertRaises(AccountingValidationError):
            compute_expected_net(100, gst=float("nan"))

    def test_rejects_infinity(self):
        with self.assertRaises(AccountingValidationError):
            compute_expected_net(float("inf"))
        with self.assertRaises(AccountingValidationError):
            compute_expected_net(100, tds=float("-inf"))

    def test_rejects_negative_adjustment_by_default(self):
        with self.assertRaises(AccountingValidationError):
            compute_expected_net(100, tds=-50)


class TestComputeSettlement(unittest.TestCase):
    """Full settlement classification with variance and evidence."""

    def _assert_explained(self, s: SettlementBreakdown):
        self.assertEqual(s.status, STATUS_EXPLAINED)
        self.assertEqual(s.reason, REASON_FULLY_EXPLAINED)
        self.assertIsNotNone(s.expected_net_amount)
        self.assertIsNotNone(s.actual_bank_amount)
        self.assertLessEqual(abs(s.remaining_variance or 0), 0.01)

    def _assert_unexplained(self, s: SettlementBreakdown, reason: str):
        self.assertEqual(s.status, STATUS_UNEXPLAINED)
        self.assertEqual(s.reason, reason)

    def test_exact_no_adjustments(self):
        # gross = bank, no accounting signals
        s = compute_settlement(10000, actual_bank=10000)
        self.assertEqual(s.status, STATUS_EXACT)
        self.assertIsNone(s.reason)

    def test_gst_explained_variance(self):
        # gateway 10000, GST 1800, bank receives 11800
        s = compute_settlement(10000, gst=1800, taxable=10000, actual_bank=11800,
                               source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self._assert_explained(s)
        self.assertEqual(s.gst_amount, 1800.0)
        self.assertEqual(s.gst_consistency, GST_CONSISTENT)
        self.assertEqual(s.expected_net_amount, 11800.0)

    def test_gst_inconsistent_contradictory(self):
        # claimed GST 100 on taxable 10000, but bank is 11800 (should be 10100)
        s = compute_settlement(10000, gst=100, taxable=10000, actual_bank=11800)
        self._assert_unexplained(s, REASON_CONTRADICTORY_EVIDENCE)
        self.assertEqual(s.gst_consistency, GST_INCONSISTENT)

    def test_tds_explained(self):
        s = compute_settlement(50000, tds=500, actual_bank=49500,
                               source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self._assert_explained(s)
        self.assertEqual(s.tds_amount, 500.0)
        self.assertEqual(s.expected_net_amount, 49500.0)

    def test_mdr_fee_explained(self):
        s = compute_settlement(10000, mdr=150, mdr_gst=27, fee=0, actual_bank=9823,
                               source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self._assert_explained(s)
        self.assertEqual(s.mdr_amount, 150.0)
        self.assertEqual(s.mdr_gst_amount, 27.0)
        self.assertEqual(s.fee_amount, 0.0)
        self.assertEqual(s.total_fee_amount, 177.0)
        self.assertEqual(s.expected_net_amount, 9823.0)

    def test_mdr_fee_tax_alias(self):
        s = compute_settlement(10000, mdr=150, mdr_gst=27, fee=0, actual_bank=9823)
        self.assertEqual(s.fee_tax_amount, s.mdr_gst_amount)  # alias

    def test_full_refund_explained(self):
        # original 1000, full refund 1000 -> bank 0
        s = compute_settlement(1000, refund=1000, actual_bank=0)
        self._assert_explained(s)
        self.assertEqual(s.refund_amount, 1000.0)
        self.assertEqual(s.expected_net_amount, 0.0)

    def test_partial_refund_explained(self):
        # original 1000, partial refund 300 -> bank 700
        s = compute_settlement(1000, refund=300, actual_bank=700)
        self._assert_explained(s)
        self.assertEqual(s.refund_amount, 300.0)
        self.assertEqual(s.expected_net_amount, 700.0)

    def test_unexplained_no_accounting_evidence(self):
        s = compute_settlement(10000, actual_bank=9900)
        self._assert_unexplained(s, REASON_NO_ACCOUNTING_EVIDENCE)
        self.assertEqual(s.remaining_variance, 100.0)

    def test_unexplained_with_adjustments_but_residual_variance(self):
        s = compute_settlement(10000, tds=500, actual_bank=48000)
        # expected 9500, actual 48000 (nonsense large diff for test)
        self._assert_unexplained(s, REASON_UNEXPLAINED_VARIANCE)

    def test_refund_exceeds_gross_flagged(self):
        s = compute_settlement(1000, refund=1500, actual_bank=0)
        self._assert_unexplained(s, REASON_REFUND_EXCEEDS_GROSS)

    def test_evidence_structure(self):
        s = compute_settlement(10000, gst=1800, taxable=10000, actual_bank=11800,
                               source_rows={"gateway": "G001", "ledger": "L001", "bank": "B001"})
        ev = s.evidence
        # Check each adjustment has traceable evidence
        types = {e["adjustment"] for e in ev if "adjustment" in e}
        self.assertIn("GROSS", types)
        self.assertIn("GST", types)
        # GST decomposition corroboration present
        decomp = next(e for e in ev if "gst_decomposition" in e)
        self.assertEqual(decomp["gst_decomposition"]["gst_evidence"], GST_CONSISTENT)

    def test_no_double_count_gst(self):
        # If gross is already GST-inclusive (gst=0), no GST is added
        s = compute_settlement(11800, gst=0, actual_bank=11800)
        self.assertEqual(s.gst_amount, 0.0)
        self.assertEqual(s.expected_net_amount, 11800.0)
        # No adjustments -> EXACT, not EXPLAINED
        self.assertEqual(s.status, STATUS_EXACT)

    def test_no_actual_bank_provided(self):
        # Without actual bank, classification reflects adjustments only
        s = compute_settlement(10000, tds=500)
        self.assertEqual(s.status, STATUS_EXPLAINED)
        self.assertIsNone(s.actual_bank_amount)
        self.assertIsNone(s.remaining_variance)
        self.assertIsNone(s.variance)


class TestBuildSettlementFromLedger(unittest.TestCase):
    """Convenience wrapper reading tax_fields from a ledger-like object."""

    def _make_ledger(self, tax_fields=None, amount=50000):
        class _Amt:
            def __init__(self, n): self.normalized = n
        class _TF:
            def __init__(self, d): self.normalized = d
        class _Rec:
            def __init__(self):
                self.tax_fields = {}
                self.amount = _Amt(amount)
        rec = _Rec()
        if tax_fields:
            for k, v in tax_fields.items():
                rec.tax_fields[k] = _TF(v)
        return rec

    def test_tds_from_ledger(self):
        ledger = self._make_ledger({"tds_amount": 500})
        s = build_settlement_from_ledger(50000, ledger, actual_bank=49500,
                                         source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self.assertEqual(s.tds_amount, 500.0)
        self.assertEqual(s.status, STATUS_EXPLAINED)

    def test_gst_from_ledger(self):
        ledger = self._make_ledger({"gst_amount": 1800})
        s = build_settlement_from_ledger(10000, ledger, actual_bank=11800,
                                         source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self.assertEqual(s.gst_amount, 1800.0)
        self.assertEqual(s.status, STATUS_EXPLAINED)
        # GST consistency: taxable(10000) + gst(1800) == actual_bank(11800)
        self.assertEqual(s.gst_consistency, GST_CONSISTENT)

    def test_mdr_fee_from_ledger(self):
        ledger = self._make_ledger({"mdr_amount": 150, "mdr_gst": 27, "fee_amount": 0})
        s = build_settlement_from_ledger(10000, ledger, actual_bank=9823,
                                         source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self.assertEqual(s.mdr_amount, 150.0)
        self.assertEqual(s.mdr_gst_amount, 27.0)
        self.assertEqual(s.fee_amount, 0.0)
        self.assertEqual(s.status, STATUS_EXPLAINED)

    def test_refund_from_negative_ledger_amount(self):
        # Refund ledger entries carry negative recorded_amount
        class _Amt:
            def __init__(self, n): self.normalized = n
        class _Rec:
            def __init__(self):
                self.tax_fields = {}
                self.amount = _Amt(-300.00)  # partial refund
        ledger = _Rec()
        s = build_settlement_from_ledger(1000, ledger, actual_bank=700,
                                         source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self.assertEqual(s.refund_amount, 300.0)
        self.assertEqual(s.status, STATUS_EXPLAINED)

    def test_refund_with_tds_from_ledger(self):
        # Refund ledger row can also carry TDS/tax fields — both adjustments apply
        class _Amt:
            def __init__(self, n): self.normalized = n
        class _TF:
            def __init__(self, d): self.normalized = d
        class _Rec:
            def __init__(self):
                self.tax_fields = {"tds_amount": _TF(50)}
                self.amount = _Amt(-300.00)  # partial refund
        ledger = _Rec()
        # gross 1000 - tds 50 - refund 300 = 650 expected bank
        s = build_settlement_from_ledger(1000, ledger, actual_bank=650,
                                         source_rows={"gateway": "G1", "ledger": "L1", "bank": "B1"})
        self.assertEqual(s.refund_amount, 300.0)
        self.assertEqual(s.tds_amount, 50.0)
        self.assertEqual(s.expected_net_amount, 650.0)
        self.assertEqual(s.status, STATUS_EXPLAINED)

    def test_missing_fields_default_to_zero(self):
        ledger = self._make_ledger({})  # empty tax_fields
        s = build_settlement_from_ledger(10000, ledger, actual_bank=10000)
        self.assertEqual(s.gst_amount, 0.0)
        self.assertEqual(s.tds_amount, 0.0)
        self.assertEqual(s.mdr_amount, 0.0)
        # No adjustments found -> EXACT
        self.assertEqual(s.status, STATUS_EXACT)


class TestSettlementBreakdownToDict(unittest.TestCase):
    """Serialization sanity."""

    def test_to_dict_contains_all_fields(self):
        s = compute_settlement(10000, tds=500, actual_bank=9500)
        d = s.to_dict()
        self.assertIn("gross_amount", d)
        self.assertIn("tds_amount", d)
        self.assertIn("expected_net_amount", d)
        self.assertIn("actual_bank_amount", d)
        self.assertIn("variance", d)
        self.assertIn("status", d)
        self.assertIn("reason", d)
        self.assertIn("evidence", d)
        self.assertIsInstance(d["evidence"], list)


if __name__ == "__main__":
    unittest.main()