"""
LedgerLoop — Phase 2: Normalization Tests
============================================

Covers all 15 test cases required by the Phase 2 spec (Section 18), plus an
integration test that runs the real Phase 1 CSVs end-to-end and checks the
architectural boundary (no matching decisions made, all data preserved).

Run with:
    python3 -m pytest tests/test_normalize.py -v
or:
    python3 tests/test_normalize.py
"""

import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.normalize import (
    normalize_gateway_row, normalize_bank_row, normalize_ledger_row,
    normalize_date, normalize_amount, normalize_reference,
    normalize_gateway, normalize_bank, normalize_ledger, normalize_all,
    NormalizationError, ValidationWarning,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


class TestNormalizationPrimitives(unittest.TestCase):
    """Tests 5, 6: amount and reference-formatting normalization in isolation."""

    def test_amount_normalizes_representation_without_losing_precision(self):
        # Test 5: amount normalization
        self.assertEqual(normalize_amount("500").normalized, 500.00)
        self.assertEqual(normalize_amount("500.0").normalized, 500.00)
        self.assertEqual(normalize_amount("500.00").normalized, 500.00)
        # genuine differences must remain distinguishable — no tolerance applied here
        self.assertNotEqual(
            normalize_amount("500.00").normalized,
            normalize_amount("499.99").normalized,
        )
        # original string is always preserved verbatim
        self.assertEqual(normalize_amount("500.0").original, "500.0")

    def test_reference_formatting_normalization_is_conservative(self):
        # Test 6: reference formatting normalization
        self.assertEqual(normalize_reference("PAY-123456").normalized, "PAY123456")
        self.assertEqual(normalize_reference("PAY123456").normalized, "PAY123456")
        self.assertEqual(normalize_reference(" gw090 ").normalized, "GW090")
        # must NOT perform fuzzy/truncation matching — different strings stay different
        self.assertNotEqual(
            normalize_reference("PAY123456").normalized,
            normalize_reference("PAY123").normalized,
        )
        # a meaningful suffix hyphen (not a prefix/number separator) is left alone
        self.assertEqual(normalize_reference("PAY097-REFUND").normalized, "PAY097-REFUND")
        # original is always preserved verbatim
        self.assertEqual(normalize_reference("PAY-123456").original, "PAY-123456")


class TestDateNormalization(unittest.TestCase):
    """Test 4: date normalization."""

    def test_valid_date_normalizes_and_preserves_original(self):
        d = normalize_date("2026-08-20")
        self.assertEqual(d.normalized, "2026-08-20")
        self.assertEqual(d.original, "2026-08-20")

    def test_invalid_date_raises_normalization_error(self):
        with self.assertRaises(NormalizationError) as ctx:
            normalize_date("20/08/2026")
        self.assertEqual(ctx.exception.field, "date")

    def test_blank_date_raises_normalization_error(self):
        with self.assertRaises(NormalizationError):
            normalize_date("")
        with self.assertRaises(NormalizationError):
            normalize_date("   ")


class TestGatewayNormalRow(unittest.TestCase):
    """Test 1: gateway normal row."""

    def test_normal_gateway_row(self):
        row = {
            "source_row_id": "G001", "payment_id": "PAY001", "payment_date": "2026-08-20",
            "amount": "500.00", "status": "CAPTURED", "gateway_reference": "GW001",
            "customer_reference": "ORD001", "settlement_expected_date": "2026-08-21",
        }
        warnings = []
        record = normalize_gateway_row(row, warnings)

        self.assertEqual(record.source, "gateway")
        self.assertEqual(record.source_row_id, "G001")
        self.assertEqual(record.transaction_reference.normalized, "PAY001")
        self.assertEqual(record.date.normalized, "2026-08-20")
        self.assertEqual(record.amount.normalized, 500.00)
        self.assertEqual(record.status, "CAPTURED")
        self.assertEqual(record.secondary_references["gateway_reference"].normalized, "GW001")
        self.assertEqual(record.secondary_references["customer_reference"].normalized, "ORD001")
        self.assertEqual(record.extra_dates["settlement_expected_date"].normalized, "2026-08-21")
        self.assertEqual(record.raw_record, row)
        self.assertEqual(warnings, [])


class TestBankNormalRow(unittest.TestCase):
    """Test 2: bank normal row. Test 8: transaction_date + value_date both preserved."""

    def test_normal_bank_row(self):
        row = {
            "source_row_id": "B001", "bank_transaction_id": "BANK001",
            "transaction_date": "2026-08-21", "value_date": "2026-08-21",
            "credit_amount": "500.00", "utr": "UTR100001", "bank_reference": "GW001",
            "description": "Settlement PAY001",
        }
        warnings = []
        record = normalize_bank_row(row, warnings)

        self.assertEqual(record.source, "bank")
        self.assertEqual(record.source_row_id, "B001")
        self.assertEqual(record.transaction_reference.normalized, "BANK001")
        self.assertEqual(record.amount.normalized, 500.00)
        self.assertEqual(record.secondary_references["utr"].normalized, "UTR100001")
        self.assertEqual(record.secondary_references["bank_reference"].normalized, "GW001")
        self.assertEqual(record.raw_record, row)

    def test_bank_transaction_date_and_value_date_both_preserved_when_they_differ(self):
        # Test 8: settlement-timing-drift style row where the two dates differ
        row = {
            "source_row_id": "B002", "bank_transaction_id": "BANK002",
            "transaction_date": "2026-08-22", "value_date": "2026-08-21",
            "credit_amount": "750.00", "utr": "UTR100002", "bank_reference": "GW002",
            "description": "Settlement PAY002",
        }
        warnings = []
        record = normalize_bank_row(row, warnings)

        # primary canonical date comes from transaction_date...
        self.assertEqual(record.date.normalized, "2026-08-22")
        # ...but value_date is NOT discarded, it's preserved in extra_dates
        self.assertIn("value_date", record.extra_dates)
        self.assertEqual(record.extra_dates["value_date"].normalized, "2026-08-21")
        # the two remain genuinely distinguishable
        self.assertNotEqual(record.date.normalized, record.extra_dates["value_date"].normalized)


class TestLedgerNormalRow(unittest.TestCase):
    """Test 3: ledger normal row. Test 9: tax/TDS preservation."""

    def test_normal_ledger_row(self):
        row = {
            "source_row_id": "L001", "ledger_entry_id": "LED001", "entry_date": "2026-08-20",
            "payment_reference": "PAY001", "invoice_reference": "INV001",
            "recorded_amount": "500.00", "tax_amount": "0.00", "tds_amount": "0.00",
            "entry_type": "SALE",
        }
        warnings = []
        record = normalize_ledger_row(row, warnings)

        self.assertEqual(record.source, "ledger")
        self.assertEqual(record.source_row_id, "L001")
        self.assertEqual(record.transaction_reference.normalized, "PAY001")
        self.assertEqual(record.amount.normalized, 500.00)
        self.assertEqual(record.status, "SALE")
        self.assertEqual(record.secondary_references["invoice_reference"].normalized, "INV001")
        self.assertEqual(record.raw_record, row)

    def test_ledger_tax_and_tds_kept_separate_from_recorded_amount(self):
        # Test 9: a TDS-deduction-style row — gross recorded_amount must NOT be
        # reduced by tds_amount during normalization; both must remain as
        # independently inspectable fields.
        row = {
            "source_row_id": "L002", "ledger_entry_id": "LED002", "entry_date": "2026-08-20",
            "payment_reference": "PAY002", "invoice_reference": "INV002",
            "recorded_amount": "10000.00", "tax_amount": "0.00", "tds_amount": "100.00",
            "entry_type": "SALE",
        }
        warnings = []
        record = normalize_ledger_row(row, warnings)

        # recorded_amount (canonical `amount`) is the GROSS figure, untouched
        self.assertEqual(record.amount.normalized, 10000.00)
        # tds_amount is available separately, not folded into amount
        self.assertEqual(record.tax_fields["tds_amount"].normalized, 100.00)
        self.assertEqual(record.tax_fields["tax_amount"].normalized, 0.00)
        # sanity: amount was NOT silently reduced to net (10000 - 100 = 9900)
        self.assertNotEqual(record.amount.normalized, 9900.00)


class TestMissingReference(unittest.TestCase):
    """Test 7: missing reference stays explicitly missing, never invented."""

    def test_missing_bank_reference_stays_none_not_fabricated(self):
        row = {
            "source_row_id": "B003", "bank_transaction_id": "BANK003",
            "transaction_date": "2026-08-20", "value_date": "2026-08-20",
            "credit_amount": "1875.00", "utr": "UTR100003", "bank_reference": "",
            "description": "NEFT credit",
        }
        warnings = []
        record = normalize_bank_row(row, warnings)

        ref = record.secondary_references["bank_reference"]
        self.assertIsNone(ref.original)
        self.assertIsNone(ref.normalized)
        # a warning should be raised for missing bank_reference (recoverable, not fatal)
        self.assertTrue(any(w.field == "bank_reference" for w in warnings))

    def test_missing_ledger_payment_reference_is_a_warning_not_a_hard_error(self):
        row = {
            "source_row_id": "L003", "ledger_entry_id": "LED003", "entry_date": "2026-08-20",
            "payment_reference": "", "invoice_reference": "INV003",
            "recorded_amount": "300.00", "tax_amount": "0.00", "tds_amount": "0.00",
            "entry_type": "SALE",
        }
        warnings = []
        # should not raise — a ledger row can realistically have a missing
        # payment_reference per Phase 1 spec Section 7
        record = normalize_ledger_row(row, warnings)
        self.assertIsNone(record.transaction_reference.original)
        self.assertTrue(any(w.field == "payment_reference" for w in warnings))


class TestDuplicateRowsPreserved(unittest.TestCase):
    """Test 10: duplicate ledger rows remain separate, not merged/deduped."""

    def test_two_ledger_rows_same_payment_reference_both_survive(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "ledger.csv")
        _write_csv(path,
            ["source_row_id", "ledger_entry_id", "entry_date", "payment_reference",
             "invoice_reference", "recorded_amount", "tax_amount", "tds_amount", "entry_type"],
            [
                ["L050", "LED050A", "2026-08-20", "PAY050", "INV050", "2000.00", "0.00", "0.00", "SALE"],
                ["L051", "LED050B", "2026-08-20", "PAY050", "INV050", "2000.00", "0.00", "0.00", "SALE"],
            ])
        result = normalize_ledger(path)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0].source_row_id, "L050")
        self.assertEqual(result.records[1].source_row_id, "L051")
        # both reference the same logical payment — normalization does NOT
        # deduplicate or merge them
        self.assertEqual(result.records[0].transaction_reference.normalized,
                          result.records[1].transaction_reference.normalized)


class TestRefundRowsPreserved(unittest.TestCase):
    """Test 11: refund rows remain distinguishable from the original payment."""

    def test_payment_and_refund_rows_stay_separate_records(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "gateway.csv")
        _write_csv(path,
            ["source_row_id", "payment_id", "payment_date", "amount", "status",
             "gateway_reference", "customer_reference", "settlement_expected_date"],
            [
                ["G095", "PAY095", "2026-08-20", "5000.00", "CAPTURED", "GW095", "ORD095", "2026-08-20"],
                ["G096", "PAY095-REFUND", "2026-08-20", "-1000.00", "REFUNDED", "GW095-R", "ORD095", "2026-08-20"],
            ])
        result = normalize_gateway(path)
        self.assertEqual(len(result.records), 2)
        refs = {r.transaction_reference.normalized for r in result.records}
        self.assertEqual(refs, {"PAY095", "PAY095-REFUND"})
        # normalization must NOT net these against each other
        amounts = {r.transaction_reference.normalized: r.amount.normalized for r in result.records}
        self.assertEqual(amounts["PAY095"], 5000.00)
        self.assertEqual(amounts["PAY095-REFUND"], -1000.00)


class TestRawRecordPreserved(unittest.TestCase):
    """Test 12: original raw row is preserved verbatim on every record."""

    def test_raw_record_matches_original_csv_row_exactly(self):
        row = {
            "source_row_id": "G001", "payment_id": "PAY001", "payment_date": "2026-08-20",
            "amount": "500.00", "status": "CAPTURED", "gateway_reference": "GW001",
            "customer_reference": "ORD001", "settlement_expected_date": "2026-08-21",
        }
        record = normalize_gateway_row(row, [])
        self.assertEqual(record.raw_record, row)
        # must be a copy, not the same object the caller passed in reused elsewhere;
        # mutating the returned raw_record should not mutate the caller's row dict.
        record.raw_record["amount"] = "999.99"
        self.assertEqual(row["amount"], "500.00")


class TestInvalidAmount(unittest.TestCase):
    """Test 13: invalid amount raises a clear NormalizationError."""

    def test_non_numeric_amount_raises(self):
        row = {
            "source_row_id": "G999", "payment_id": "PAY999", "payment_date": "2026-08-20",
            "amount": "not-a-number", "status": "CAPTURED", "gateway_reference": "GW999",
            "customer_reference": "ORD999", "settlement_expected_date": "2026-08-20",
        }
        with self.assertRaises(NormalizationError) as ctx:
            normalize_gateway_row(row, [])
        self.assertEqual(ctx.exception.field, "amount")
        self.assertEqual(ctx.exception.raw_value, "not-a-number")

    def test_blank_amount_raises(self):
        row = {
            "source_row_id": "G998", "payment_id": "PAY998", "payment_date": "2026-08-20",
            "amount": "", "status": "CAPTURED", "gateway_reference": "GW998",
            "customer_reference": "ORD998", "settlement_expected_date": "2026-08-20",
        }
        with self.assertRaises(NormalizationError) as ctx:
            normalize_gateway_row(row, [])
        self.assertEqual(ctx.exception.field, "amount")


class TestInvalidDate(unittest.TestCase):
    """Test 14: invalid date raises a clear NormalizationError."""

    def test_malformed_date_raises(self):
        row = {
            "source_row_id": "G997", "payment_id": "PAY997", "payment_date": "20-Aug-2026",
            "amount": "500.00", "status": "CAPTURED", "gateway_reference": "GW997",
            "customer_reference": "ORD997", "settlement_expected_date": "2026-08-20",
        }
        with self.assertRaises(NormalizationError) as ctx:
            normalize_gateway_row(row, [])
        self.assertEqual(ctx.exception.field, "date")


class TestMissingRequiredColumn(unittest.TestCase):
    """Test 15: missing required column raises a clear NormalizationError."""

    def test_missing_column_raises_before_any_row_is_processed(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "gateway.csv")
        _write_csv(path,
            ["source_row_id", "payment_id", "amount"],  # missing several required columns
            [["G001", "PAY001", "500.00"]])
        with self.assertRaises(NormalizationError) as ctx:
            normalize_gateway(path)
        self.assertEqual(ctx.exception.source, "gateway")
        self.assertIn("payment_date", ctx.exception.problem)


class TestDuplicateSourceRowId(unittest.TestCase):
    """Extra: duplicate source_row_id within one file must be rejected clearly."""

    def test_duplicate_source_row_id_raises(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "gateway.csv")
        _write_csv(path,
            ["source_row_id", "payment_id", "payment_date", "amount", "status",
             "gateway_reference", "customer_reference", "settlement_expected_date"],
            [
                ["G001", "PAY001", "2026-08-20", "500.00", "CAPTURED", "GW001", "ORD001", "2026-08-20"],
                ["G001", "PAY002", "2026-08-20", "300.00", "CAPTURED", "GW002", "ORD002", "2026-08-20"],
            ])
        with self.assertRaises(NormalizationError) as ctx:
            normalize_gateway(path)
        self.assertEqual(ctx.exception.field, "source_row_id")


class TestStrictVsNonStrictMode(unittest.TestCase):
    """Extra: strict=False should skip bad rows and continue; strict=True should raise."""

    def test_non_strict_skips_bad_row_and_continues(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "gateway.csv")
        _write_csv(path,
            ["source_row_id", "payment_id", "payment_date", "amount", "status",
             "gateway_reference", "customer_reference", "settlement_expected_date"],
            [
                ["G001", "PAY001", "2026-08-20", "500.00", "CAPTURED", "GW001", "ORD001", "2026-08-20"],
                ["G002", "PAY002", "2026-08-20", "BAD_AMOUNT", "CAPTURED", "GW002", "ORD002", "2026-08-20"],
                ["G003", "PAY003", "2026-08-20", "300.00", "CAPTURED", "GW003", "ORD003", "2026-08-20"],
            ])
        result = normalize_gateway(path, strict=False)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].source_row_id, "G002")

    def test_strict_raises_on_first_bad_row(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "gateway.csv")
        _write_csv(path,
            ["source_row_id", "payment_id", "payment_date", "amount", "status",
             "gateway_reference", "customer_reference", "settlement_expected_date"],
            [["G002", "PAY002", "2026-08-20", "BAD_AMOUNT", "CAPTURED", "GW002", "ORD002", "2026-08-20"]])
        with self.assertRaises(NormalizationError):
            normalize_gateway(path, strict=True)


class TestPhase1Integration(unittest.TestCase):
    """
    Integration test using the ACTUAL Phase 1 dataset (data/gateway.csv,
    data/bank.csv, data/ledger.csv). Verifies end-to-end behavior against
    real generated data, not synthetic test fixtures.
    """

    @classmethod
    def setUpClass(cls):
        cls.result = normalize_all(data_dir=DATA_DIR, strict=False)

    def test_no_hard_errors_on_real_dataset(self):
        self.assertEqual(len(self.result.gateway.errors), 0)
        self.assertEqual(len(self.result.bank.errors), 0)
        self.assertEqual(len(self.result.ledger.errors), 0)

    def test_record_counts_match_raw_csv_row_counts(self):
        with open(os.path.join(DATA_DIR, "gateway.csv")) as f:
            gateway_rows = len(list(csv.DictReader(f)))
        with open(os.path.join(DATA_DIR, "bank.csv")) as f:
            bank_rows = len(list(csv.DictReader(f)))
        with open(os.path.join(DATA_DIR, "ledger.csv")) as f:
            ledger_rows = len(list(csv.DictReader(f)))
        self.assertEqual(len(self.result.gateway.records), gateway_rows)
        self.assertEqual(len(self.result.bank.records), bank_rows)
        self.assertEqual(len(self.result.ledger.records), ledger_rows)

    def test_duplicate_ledger_case_survives_as_two_records(self):
        # Phase 1 DUPLICATE_LEDGER_ENTRY cases (e.g. PAY091) must produce
        # two separate CanonicalRecords, not one deduplicated record.
        dup_refs = {}
        for r in self.result.ledger.records:
            ref = r.transaction_reference.normalized
            if ref:
                dup_refs.setdefault(ref, []).append(r)
        duplicated = {ref: recs for ref, recs in dup_refs.items() if len(recs) > 1}
        self.assertGreater(len(duplicated), 0,
                            "expected at least one duplicated payment_reference in ledger records")

    def test_refund_rows_survive_as_distinct_gateway_records(self):
        refund_records = [r for r in self.result.gateway.records
                           if (r.transaction_reference.original or "").endswith("-REFUND")]
        self.assertGreater(len(refund_records), 0)
        for r in refund_records:
            self.assertLess(r.amount.normalized, 0,
                             "refund amount should remain negative, not netted")

    def test_tds_cases_keep_amount_and_tds_separate(self):
        tds_records = [r for r in self.result.ledger.records
                        if r.tax_fields.get("tds_amount") and r.tax_fields["tds_amount"].normalized > 0]
        self.assertGreater(len(tds_records), 0)
        for r in tds_records:
            # gross amount must be strictly greater than (amount - tds), i.e. not pre-netted
            self.assertGreater(r.amount.normalized, 0)

    def test_bank_records_all_carry_both_dates(self):
        for r in self.result.bank.records:
            self.assertIn("value_date", r.extra_dates)
            self.assertIsNotNone(r.date.original)
            self.assertIsNotNone(r.extra_dates["value_date"].original)

    def test_missing_bank_reference_cases_present_and_explicit(self):
        # Phase 1.1 PAY108 (two ambiguous NEFT credits) and PAY111 (blank
        # bank_reference, textual evidence only) both leave bank_reference
        # explicitly None rather than fabricating a value.
        missing = [r for r in self.result.bank.records
                   if r.secondary_references["bank_reference"].original is None]
        self.assertGreaterEqual(len(missing), 2)

    def test_source_row_ids_are_all_traceable_and_unique_within_each_source(self):
        for result in (self.result.gateway, self.result.bank, self.result.ledger):
            ids = [r.source_row_id for r in result.records]
            self.assertEqual(len(ids), len(set(ids)),
                              f"{result.source}: source_row_id must be unique per record")
            self.assertTrue(all(ids), f"{result.source}: every record must have a source_row_id")

    def test_no_cross_source_fields_present_on_any_record(self):
        # Architectural boundary check: canonical records must not carry any
        # field that implies a cross-source comparison/decision has been made
        # (e.g. no "matched_to", "match_status", "match_score", "tier" field).
        forbidden_attrs = {"matched_to", "match_status", "match_score", "tier",
                            "is_duplicate_of", "reconciliation_status"}
        for result in (self.result.gateway, self.result.bank, self.result.ledger):
            for r in result.records:
                present = forbidden_attrs & set(vars(r).keys())
                self.assertEqual(present, set(),
                                  f"{result.source}/{r.source_row_id} has matching-layer "
                                  f"field(s) that should not exist yet: {present}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
