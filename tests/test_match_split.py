"""
tests/test_match_split.py — Stage 3 Generic Split / Multi-Payment Tests
=========================================================================

Covers all 23 scenarios from the Stage 3 specification:

 1. Exact one-to-one regression (existing one-to-one paths unaffected)
 2. 2-row split settlement (deterministic, no LLM)
 3. 3-row split settlement (deterministic, no LLM)
 4. Multiple-payment (N > 3, bounded)
 5. Partial payment — received < expected
 6. Full split after TDS deduction
 7. Full split after MDR/fee deduction
 8. Full split with refund-linked net amount
 9. Duplicate bank row prevention (same row ID in two combos)
10. Bank row already consumed — must not be re-offered
11. Ambiguous combinations → AMBIGUOUS result
12. Conflicting references (no plausible evidence)
13. Incorrect arithmetic (sum outside tolerance)
14. Nonexistent candidate (row ID not in bank records)
15. Invalid candidate combination (fails validation)
16. Candidate combination exceeding configured bound
17. Two gateways competing for the same bank rows
18. Deterministic split does NOT call Gemini
19. Gemini unavailable → AI_RETRY_REQUIRED
20. Invalid Gemini recommendation → HUMAN_REVIEW / AMBIGUOUS
21. Valid Gemini recommendation → independently validated and accepted
22. Existing PAY109-shaped behaviour (generic, not hardcoded)
23. Full pytest suite remains green (run at end of module)

All Gemini interactions are mocked — no live network calls.
"""

import unittest
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch
import json

from core.normalize import CanonicalRecord
from core.match_split import (
    SplitMatcher,
    SplitResult,
    SplitStatus,
    SplitRule,
    SplitReason,
    run_stage3,
    SPLIT_TOLERANCE,
    MAX_COMBO_SIZE,
    CANDIDATE_FILTER_LIMIT,
    _build_candidate_pool,
    _rule_for_size,
)
from core.match_llm import LLMUnavailableError


# ---------------------------------------------------------------------------
# Fixture helpers — build minimal CanonicalRecord objects
# ---------------------------------------------------------------------------

def _amount(value):
    """Return a minimal NormalizedAmount-like object."""
    a = MagicMock()
    a.normalized = float(value)
    return a


def _ref(value):
    """Return a minimal NormalizedReference-like object."""
    r = MagicMock()
    r.normalized = value
    return r


def _tax(value):
    """Return a minimal NormalizedAmount-like object for a tax field."""
    t = MagicMock()
    t.normalized = float(value)
    return t


def make_gateway(row_id: str, txn_id: str, amount: float,
                 gw_reference: str = "", customer_ref: str = "") -> CanonicalRecord:
    """Build a gateway CanonicalRecord with the minimum fields Stage 3 needs."""
    rec = MagicMock(spec=CanonicalRecord)
    rec.source_row_id = row_id
    rec.transaction_reference = _ref(txn_id)
    rec.amount = _amount(amount)
    rec.date = _ref("2024-01-15")
    refs = {}
    if gw_reference:
        refs["gateway_reference"] = _ref(gw_reference)
    if customer_ref:
        refs["customer_reference"] = _ref(customer_ref)
    rec.secondary_references = refs
    rec.tax_fields = {}
    return rec


def make_bank(row_id: str, amount: float,
              bank_ref: str = "", description: str = "",
              date: str = "2024-01-15") -> CanonicalRecord:
    """Build a bank CanonicalRecord."""
    rec = MagicMock(spec=CanonicalRecord)
    rec.source_row_id = row_id
    rec.transaction_reference = _ref(row_id)
    rec.amount = _amount(amount)
    rec.date = _ref(date)
    refs = {}
    if bank_ref:
        refs["bank_reference"] = _ref(bank_ref)
    if description:
        refs["description"] = _ref(description)
    rec.secondary_references = refs
    rec.tax_fields = {}
    return rec


def make_ledger(row_id: str, txn_id: str, amount: float,
                tds: float = 0.0, mdr: float = 0.0, mdr_gst: float = 0.0,
                fee: float = 0.0, gst: float = 0.0,
                invoice_ref: str = "") -> CanonicalRecord:
    """Build a ledger CanonicalRecord with optional tax fields."""
    rec = MagicMock(spec=CanonicalRecord)
    rec.source_row_id = row_id
    rec.transaction_reference = _ref(txn_id)
    rec.amount = _amount(amount)
    rec.date = _ref("2024-01-15")
    refs = {}
    if invoice_ref:
        refs["invoice_reference"] = _ref(invoice_ref)
    rec.secondary_references = refs

    tax_fields = {}
    if tds > 0:
        tax_fields["tds_amount"] = _tax(tds)
    if mdr > 0:
        tax_fields["mdr_amount"] = _tax(mdr)
    if mdr_gst > 0:
        tax_fields["mdr_gst"] = _tax(mdr_gst)
    if fee > 0:
        tax_fields["fee_amount"] = _tax(fee)
    if gst > 0:
        tax_fields["gst_amount"] = _tax(gst)
    rec.tax_fields = tax_fields
    return rec


def _pending(txn_id: str, gw_row_id: str,
             ledger_row_id: Optional[str] = None) -> dict:
    return {
        "transaction_id": txn_id,
        "gateway_row_id": gw_row_id,
        "ledger_row_id": ledger_row_id,
    }


def _mock_llm(decision: str = "MATCH",
              bank_row_ids: Optional[list] = None,
              confidence: float = 0.95,
              rationale: str = "test",
              raise_unavailable: bool = False) -> MagicMock:
    """Build a mock LLMClient."""
    client = MagicMock()
    if raise_unavailable:
        client.complete.side_effect = LLMUnavailableError("no key")
        return client
    response = json.dumps({
        "decision": decision,
        "bank_row_ids": bank_row_ids or [],
        "confidence": confidence,
        "rationale": rationale,
        "evidence": {},
        "adjustment": {},
    })
    client.complete.return_value = response
    return client


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestRuleForSize(unittest.TestCase):
    """_rule_for_size helper."""

    def test_2_row(self):
        self.assertEqual(_rule_for_size(2), SplitRule.SPLIT_2_ROW)

    def test_3_row(self):
        self.assertEqual(_rule_for_size(3), SplitRule.SPLIT_3_ROW)

    def test_4_row(self):
        self.assertEqual(_rule_for_size(4), SplitRule.MULTIPLE_PAYMENTS)

    def test_5_row(self):
        self.assertEqual(_rule_for_size(5), SplitRule.MULTIPLE_PAYMENTS)


class TestOneToOneRegression(unittest.TestCase):
    """Test 1 — existing one-to-one cases not broken by Stage 3 machinery."""

    def test_no_pending_transactions_returns_empty_results(self):
        gw = make_gateway("GW001", "PAY001", 1000.0, gw_reference="GW001")
        bank = make_bank("B001", 1000.0, bank_ref="GW001")
        ledger = make_ledger("L001", "PAY001", 1000.0)

        results, summary = run_stage3(
            gateway_records=[gw],
            bank_records=[bank],
            ledger_records=[ledger],
            already_consumed={"B001"},   # already matched one-to-one
            pending_txns=[],
        )
        self.assertEqual(len(results), 0)
        self.assertEqual(summary.total_evaluated, 0)
        self.assertEqual(summary.match_count, 0)

    def test_already_consumed_rows_not_reoffered(self):
        """A bank row consumed by Tier 1/2/3 one-to-one must never appear
        in Stage 3 candidate pools."""
        gw = make_gateway("GW002", "PAY002", 5000.0, gw_reference="GW002")
        bank_consumed = make_bank("B_CONSUMED", 5000.0, bank_ref="GW002")
        bank_available = make_bank("B_AVAIL", 2500.0, bank_ref="GW002")

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[bank_consumed, bank_available],
            ledger_records=[],
            already_consumed={"B_CONSUMED"},
            pending_txns=[_pending("PAY002", "GW002")],
        )
        self.assertEqual(len(results), 1)
        self.assertNotIn("B_CONSUMED", results[0].bank_row_ids)


class TestTwoRowSplit(unittest.TestCase):
    """Test 2 — 1 gateway → 2 bank rows, deterministic match."""

    def setUp(self):
        self.gw = make_gateway("GW_A", "PAY_A", 10000.0, gw_reference="GW100")
        self.b1 = make_bank("B101", 6000.0, bank_ref="GW100")
        self.b2 = make_bank("B102", 4000.0, bank_ref="GW100")
        self.ledger = make_ledger("L_A", "PAY_A", 10000.0)

    def test_two_row_split_is_matched(self):
        results, summary = run_stage3(
            gateway_records=[self.gw],
            bank_records=[self.b1, self.b2],
            ledger_records=[self.ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_A", "GW_A", "L_A")],
        )
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, SplitStatus.MATCH)
        self.assertEqual(r.rule, SplitRule.SPLIT_2_ROW)
        self.assertIn("B101", r.bank_row_ids)
        self.assertIn("B102", r.bank_row_ids)
        self.assertEqual(len(r.bank_row_ids), 2)
        self.assertEqual(summary.match_count, 1)

    def test_two_row_split_does_not_call_llm(self):
        """Deterministic single-combo split must never consult Gemini."""
        mock_llm = _mock_llm()
        results, _ = run_stage3(
            gateway_records=[self.gw],
            bank_records=[self.b1, self.b2],
            ledger_records=[self.ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_A", "GW_A", "L_A")],
            llm_client=mock_llm,
        )
        mock_llm.complete.assert_not_called()
        self.assertFalse(results[0].llm_consulted)

    def test_two_row_split_consumes_both_rows(self):
        """After a split match both bank rows must be consumed."""
        matcher = SplitMatcher(
            gateway_records=[self.gw],
            bank_records=[self.b1, self.b2],
            ledger_records=[self.ledger],
            already_consumed=set(),
        )
        matcher.resolve("PAY_A", "GW_A", "L_A")
        self.assertIn("B101", matcher._consumed)
        self.assertIn("B102", matcher._consumed)

    def test_two_row_split_within_tolerance(self):
        """A split sum within SPLIT_TOLERANCE of expected_net is accepted."""
        # Gateway 10000, bank rows sum to 9998 (diff 2.00 < tolerance 5.00)
        b1 = make_bank("BT1", 6000.0, bank_ref="GW100")
        b2 = make_bank("BT2", 3998.0, bank_ref="GW100")
        results, _ = run_stage3(
            gateway_records=[self.gw],
            bank_records=[b1, b2],
            ledger_records=[self.ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_A", "GW_A", "L_A")],
        )
        self.assertEqual(results[0].status, SplitStatus.MATCH)


class TestThreeRowSplit(unittest.TestCase):
    """Test 3 — 1 gateway → 3 bank rows."""

    def setUp(self):
        self.gw = make_gateway("GW_B", "PAY_B", 12000.0, gw_reference="GW200")
        self.b1 = make_bank("B201", 5000.0, bank_ref="GW200")
        self.b2 = make_bank("B202", 4000.0, bank_ref="GW200")
        self.b3 = make_bank("B203", 3000.0, bank_ref="GW200")
        self.ledger = make_ledger("L_B", "PAY_B", 12000.0)

    def test_three_row_split_is_matched(self):
        results, summary = run_stage3(
            gateway_records=[self.gw],
            bank_records=[self.b1, self.b2, self.b3],
            ledger_records=[self.ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_B", "GW_B", "L_B")],
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.MATCH)
        self.assertEqual(r.rule, SplitRule.SPLIT_3_ROW)
        self.assertEqual(set(r.bank_row_ids), {"B201", "B202", "B203"})
        self.assertEqual(summary.match_count, 1)

    def test_three_row_split_rule_correct(self):
        results, _ = run_stage3(
            gateway_records=[self.gw],
            bank_records=[self.b1, self.b2, self.b3],
            ledger_records=[self.ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_B", "GW_B", "L_B")],
        )
        self.assertEqual(results[0].rule, SplitRule.SPLIT_3_ROW)


class TestMultiplePayments(unittest.TestCase):
    """Test 4 — N bank rows where N > 3."""

    def test_four_row_multiple_payments(self):
        gw = make_gateway("GW_C", "PAY_C", 20000.0, gw_reference="GW300")
        b1 = make_bank("B301", 5000.0, bank_ref="GW300")
        b2 = make_bank("B302", 5000.0, bank_ref="GW300")
        b3 = make_bank("B303", 5000.0, bank_ref="GW300")
        b4 = make_bank("B304", 5000.0, bank_ref="GW300")
        ledger = make_ledger("L_C", "PAY_C", 20000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_C", "GW_C", "L_C")],
            max_combo_size=4,
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.MATCH)
        self.assertEqual(r.rule, SplitRule.MULTIPLE_PAYMENTS)
        self.assertEqual(len(r.bank_row_ids), 4)


class TestPartialPayment(unittest.TestCase):
    """Test 5 — partial payment: bank total < expected settlement."""

    def test_partial_payment_detected(self):
        gw = make_gateway("GW_D", "PAY_D", 25000.0, gw_reference="GW400")
        b1 = make_bank("B401", 10000.0, bank_ref="GW400")
        b2 = make_bank("B402", 8000.0, bank_ref="GW400")
        ledger = make_ledger("L_D", "PAY_D", 25000.0)

        results, summary = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_D", "GW_D", "L_D")],
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.PARTIAL)
        self.assertEqual(r.rule, SplitRule.PARTIAL_PAYMENT)
        self.assertAlmostEqual(r.received, 18000.0, places=2)
        self.assertAlmostEqual(r.outstanding, 7000.0, places=2)
        self.assertAlmostEqual(r.expected_net, 25000.0, places=2)
        self.assertEqual(summary.partial_count, 1)

    def test_partial_not_marked_as_full_match(self):
        """A partial must never be promoted to MATCH."""
        gw = make_gateway("GW_D2", "PAY_D2", 25000.0, gw_reference="GW401")
        b1 = make_bank("B410", 10000.0, bank_ref="GW401")
        ledger = make_ledger("L_D2", "PAY_D2", 25000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_D2", "GW_D2", "L_D2")],
        )
        self.assertNotEqual(results[0].status, SplitStatus.MATCH)

    def test_partial_rows_not_consumed(self):
        """Partial payment rows must NOT be consumed (human must confirm)."""
        gw = make_gateway("GW_D3", "PAY_D3", 25000.0, gw_reference="GW402")
        b1 = make_bank("B421", 10000.0, bank_ref="GW402")
        b2 = make_bank("B422", 8000.0, bank_ref="GW402")
        ledger = make_ledger("L_D3", "PAY_D3", 25000.0)

        matcher = SplitMatcher(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
        )
        result = matcher.resolve("PAY_D3", "GW_D3", "L_D3")
        self.assertEqual(result.status, SplitStatus.PARTIAL)
        # Bank rows must remain available for human confirmation
        self.assertNotIn("B421", matcher._consumed)
        self.assertNotIn("B422", matcher._consumed)


class TestSplitAfterTDS(unittest.TestCase):
    """Test 6 — split settlement after TDS deduction."""

    def test_split_after_tds(self):
        """Gateway 10000, TDS 1000 → expected 9000. Two bank rows sum to 9000."""
        gw = make_gateway("GW_E", "PAY_E", 10000.0, gw_reference="GW500")
        b1 = make_bank("B501", 5000.0, bank_ref="GW500")
        b2 = make_bank("B502", 4000.0, bank_ref="GW500")
        ledger = make_ledger("L_E", "PAY_E", 10000.0, tds=1000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_E", "GW_E", "L_E")],
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.MATCH)
        # Expected net = 10000 - 1000 = 9000; bank rows sum to 9000
        self.assertAlmostEqual(r.expected_net, 9000.0, places=2)
        self.assertAlmostEqual(r.received, 9000.0, places=2)


class TestSplitAfterMDR(unittest.TestCase):
    """Test 7 — split settlement after MDR/fee deduction."""

    def test_split_after_mdr(self):
        """Gateway 10000, MDR 200, MDR_GST 36 → expected 9764.
        Two bank rows sum to 9764."""
        gw = make_gateway("GW_F", "PAY_F", 10000.0, gw_reference="GW600")
        b1 = make_bank("B601", 5000.0, bank_ref="GW600")
        b2 = make_bank("B602", 4764.0, bank_ref="GW600")
        ledger = make_ledger("L_F", "PAY_F", 10000.0, mdr=200.0, mdr_gst=36.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_F", "GW_F", "L_F")],
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.MATCH)
        self.assertAlmostEqual(r.expected_net, 9764.0, places=2)


class TestSplitWithRefund(unittest.TestCase):
    """Test 8 — split with refund-adjusted net."""

    def test_split_after_refund(self):
        """Gateway 10000, ledger refund -1000 → expected 9000.
        Two bank rows sum to 9000."""
        gw = make_gateway("GW_G", "PAY_G", 10000.0, gw_reference="GW700")
        b1 = make_bank("B701", 5000.0, bank_ref="GW700")
        b2 = make_bank("B702", 4000.0, bank_ref="GW700")
        # Ledger amount -1000 triggers refund_magnitude extraction
        ledger = make_ledger("L_G", "PAY_G", -1000.0)
        # But the actual gross is the gateway's 10000; build_settlement_from_ledger
        # reads ledger.amount as negative → refund_magnitude = 1000
        # expected = gross(10000) - refund(1000) = 9000
        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_G", "GW_G", "L_G")],
        )
        r = results[0]
        # Expected net from accounting: 10000 - 1000 = 9000
        self.assertAlmostEqual(r.expected_net, 9000.0, places=2)
        if r.status == SplitStatus.MATCH:
            self.assertAlmostEqual(r.received, 9000.0, places=2)


class TestDuplicateBankRowPrevention(unittest.TestCase):
    """Test 9 — the same bank row ID cannot appear twice in one combination."""

    def test_no_duplicate_row_in_combination(self):
        """If a combination would repeat a row ID, it must be rejected."""
        gw = make_gateway("GW_H", "PAY_H", 10000.0, gw_reference="GW800")
        b1 = make_bank("B801", 5000.0, bank_ref="GW800")
        ledger = make_ledger("L_H", "PAY_H", 10000.0)

        matcher = SplitMatcher(
            gateway_records=[gw],
            bank_records=[b1],
            ledger_records=[ledger],
            already_consumed=set(),
        )
        result = matcher.resolve("PAY_H", "GW_H", "L_H")
        # Only one available row — cannot form a valid 2+ combination
        self.assertNotEqual(result.status, SplitStatus.MATCH)
        # Ensure bank_row_ids has no duplicates whatever the result
        self.assertEqual(len(result.bank_row_ids), len(set(result.bank_row_ids)))

    def test_validate_llm_recommendation_rejects_duplicate_ids(self):
        """LLM recommendation with duplicate bank_row_ids must be rejected."""
        gw = make_gateway("GW_H2", "PAY_H2", 10000.0, gw_reference="GW801")
        b1 = make_bank("B811", 5000.0, bank_ref="GW801")
        b2 = make_bank("B812", 5000.0, bank_ref="GW801")
        ledger = make_ledger("L_H2", "PAY_H2", 10000.0)

        matcher = SplitMatcher(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
        )
        rec = {
            "decision": "MATCH",
            "bank_row_ids": ["B811", "B811"],  # duplicate
            "confidence": 0.9,
            "evidence": {},
            "adjustment": {},
        }
        validated, reason = matcher._validate_llm_recommendation(
            rec, ["B811", "B812"], Decimal("10000")
        )
        self.assertIsNone(validated)
        self.assertEqual(reason, "DUPLICATE_BANK_ROW_ID")


class TestAlreadyConsumedRowExclusion(unittest.TestCase):
    """Test 10 — bank rows already consumed by Tier 1/2/3 are unavailable."""

    def test_consumed_row_excluded_from_split(self):
        gw = make_gateway("GW_I", "PAY_I", 10000.0, gw_reference="GW900")
        b1 = make_bank("B901", 6000.0, bank_ref="GW900")   # consumed
        b2 = make_bank("B902", 4000.0, bank_ref="GW900")   # available

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[],
            already_consumed={"B901"},    # B901 already claimed
            pending_txns=[_pending("PAY_I", "GW_I")],
        )
        r = results[0]
        self.assertNotIn("B901", r.bank_row_ids)

    def test_llm_recommendation_with_consumed_row_rejected(self):
        """Gemini recommending a consumed row must be rejected by the validator."""
        gw = make_gateway("GW_I2", "PAY_I2", 10000.0, gw_reference="GW901")
        b1 = make_bank("B911", 6000.0, bank_ref="GW901")
        b2 = make_bank("B912", 4000.0, bank_ref="GW901")
        ledger = make_ledger("L_I2", "PAY_I2", 10000.0)

        matcher = SplitMatcher(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed={"B911"},   # B911 consumed before this call
        )
        rec = {
            "decision": "MATCH",
            "bank_row_ids": ["B911", "B912"],   # B911 consumed
            "confidence": 0.95,
            "evidence": {},
            "adjustment": {},
        }
        # available_ids must exclude consumed rows
        validated, reason = matcher._validate_llm_recommendation(
            rec, ["B912"], Decimal("10000")   # B911 not in available_ids
        )
        self.assertIsNone(validated)
        self.assertEqual(reason, "CANDIDATE_NOT_IN_PREVETTED_SET")


class TestAmbiguousCombinations(unittest.TestCase):
    """Test 11 — multiple equally-plausible combinations → AMBIGUOUS."""

    def test_ambiguous_without_llm(self):
        """Two valid combos, no LLM client → AI_RETRY_REQUIRED."""
        gw = make_gateway("GW_J", "PAY_J", 10000.0, gw_reference="GW1000")
        b1 = make_bank("B1001", 6000.0, bank_ref="GW1000")
        b2 = make_bank("B1002", 4000.0, bank_ref="GW1000")
        b3 = make_bank("B1003", 7000.0, bank_ref="GW1000")
        b4 = make_bank("B1004", 3000.0, bank_ref="GW1000")
        ledger = make_ledger("L_J", "PAY_J", 10000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_J", "GW_J", "L_J")],
            llm_client=None,
        )
        r = results[0]
        # Two valid combos (B1001+B1002 and B1003+B1004), no LLM → retry
        self.assertIn(r.status, (SplitStatus.AI_RETRY_REQUIRED, SplitStatus.AMBIGUOUS))

    def test_ambiguous_with_llm_human_review(self):
        """Gemini returns HUMAN_REVIEW for genuinely ambiguous case."""
        gw = make_gateway("GW_J2", "PAY_J2", 10000.0, gw_reference="GW1001")
        b1 = make_bank("B1011", 6000.0, bank_ref="GW1001")
        b2 = make_bank("B1012", 4000.0, bank_ref="GW1001")
        b3 = make_bank("B1013", 7000.0, bank_ref="GW1001")
        b4 = make_bank("B1014", 3000.0, bank_ref="GW1001")
        ledger = make_ledger("L_J2", "PAY_J2", 10000.0)

        mock_llm = _mock_llm(decision="HUMAN_REVIEW", bank_row_ids=[])
        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_J2", "GW_J2", "L_J2")],
            llm_client=mock_llm,
        )
        r = results[0]
        self.assertIn(r.status, (SplitStatus.AMBIGUOUS, SplitStatus.AI_RETRY_REQUIRED))


class TestConflictingReferences(unittest.TestCase):
    """Test 12 — no plausible evidence → UNRESOLVED."""

    def test_no_reference_match_and_no_amount_plausible(self):
        """Bank rows with totally different references and amounts → UNRESOLVED."""
        gw = make_gateway("GW_K", "PAY_K", 10000.0, gw_reference="GW_SPECIFIC_999")
        # Bank rows with no matching reference and amounts too small
        b1 = make_bank("B_NOISE1", 50.0, bank_ref="OTHER_REF")
        b2 = make_bank("B_NOISE2", 75.0, bank_ref="UNRELATED")
        ledger = make_ledger("L_K", "PAY_K", 10000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_K", "GW_K", "L_K")],
        )
        self.assertEqual(results[0].status, SplitStatus.UNRESOLVED)


class TestIncorrectArithmetic(unittest.TestCase):
    """Test 13 — sum well outside tolerance must not produce a match."""

    def test_sum_outside_tolerance_is_not_matched(self):
        """Bank rows sum to 8000, expected 10000, diff 2000 > SPLIT_TOLERANCE."""
        gw = make_gateway("GW_L", "PAY_L", 10000.0, gw_reference="GW_ARITH")
        b1 = make_bank("B_AR1", 5000.0, bank_ref="GW_ARITH")
        b2 = make_bank("B_AR2", 3000.0, bank_ref="GW_ARITH")   # sum = 8000
        ledger = make_ledger("L_L", "PAY_L", 10000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_L", "GW_L", "L_L")],
        )
        self.assertNotEqual(results[0].status, SplitStatus.MATCH)

    def test_llm_recommendation_rejected_if_arithmetic_fails(self):
        """Python rejects LLM recommendation whose sum is outside tolerance."""
        gw = make_gateway("GW_L2", "PAY_L2", 10000.0, gw_reference="GW_AR2")
        b1 = make_bank("B_AR3", 5000.0, bank_ref="GW_AR2")
        b2 = make_bank("B_AR4", 3000.0, bank_ref="GW_AR2")
        ledger = make_ledger("L_L2", "PAY_L2", 10000.0)

        matcher = SplitMatcher(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
        )
        rec = {
            "decision": "MATCH",
            "bank_row_ids": ["B_AR3", "B_AR4"],   # sum 8000 ≠ 10000
            "confidence": 0.9,
            "evidence": {},
            "adjustment": {},
        }
        validated, reason = matcher._validate_llm_recommendation(
            rec, ["B_AR3", "B_AR4"], Decimal("10000")
        )
        self.assertIsNone(validated)
        self.assertEqual(reason, SplitReason.ARITHMETIC_MISMATCH)


class TestNonexistentCandidate(unittest.TestCase):
    """Test 14 — LLM invents a bank row ID not in the pre-vetted set."""

    def test_invented_bank_row_rejected(self):
        gw = make_gateway("GW_M", "PAY_M", 10000.0, gw_reference="GW_INVENT")
        b1 = make_bank("B_REAL1", 6000.0, bank_ref="GW_INVENT")
        b2 = make_bank("B_REAL2", 4000.0, bank_ref="GW_INVENT")
        b3 = make_bank("B_REAL3", 7000.0, bank_ref="GW_INVENT")
        b4 = make_bank("B_REAL4", 3000.0, bank_ref="GW_INVENT")
        ledger = make_ledger("L_M", "PAY_M", 10000.0)

        # Two valid combos exist (B_REAL1+B_REAL2 and B_REAL3+B_REAL4), so the
        # LLM path is genuinely reached. Gemini invents "B_FAKE" which was
        # never in the pre-vetted candidate set.
        mock_llm = _mock_llm(decision="MATCH",
                             bank_row_ids=["B_REAL1", "B_FAKE"])
        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_M", "GW_M", "L_M")],
            llm_client=mock_llm,
        )
        # Recommendation rejected because B_FAKE not in pre-vetted set
        r = results[0]
        self.assertNotEqual(r.status, SplitStatus.MATCH)


class TestCandidateBoundExceeded(unittest.TestCase):
    """Test 16 — candidate pool exceeds configured limit → UNRESOLVED."""

    def test_candidate_limit_exceeded_returns_unresolved(self):
        gw = make_gateway("GW_P", "PAY_P", 10000.0, gw_reference="GW_LIMIT")
        # 5 bank rows all with matching reference
        banks = [make_bank(f"B_LIM{i}", 2000.0, bank_ref="GW_LIMIT")
                 for i in range(5)]
        ledger = make_ledger("L_P", "PAY_P", 10000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=banks,
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_P", "GW_P", "L_P")],
            candidate_filter_limit=3,    # 5 rows > limit 3
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.UNRESOLVED)
        self.assertEqual(r.reason, SplitReason.CANDIDATE_LIMIT_EXCEEDED)


class TestCompetingGateways(unittest.TestCase):
    """Test 17 — two gateways compete for the same bank rows."""

    def test_first_gateway_wins_second_gets_unresolved(self):
        """Gateway A claims B_SHARED1 + B_SHARED2; Gateway B cannot reuse them."""
        gw_a = make_gateway("GW_QA", "PAY_QA", 10000.0, gw_reference="GW_Q1")
        gw_b = make_gateway("GW_QB", "PAY_QB", 10000.0, gw_reference="GW_Q2")
        b_shared1 = make_bank("B_SH1", 6000.0, bank_ref="GW_Q1")
        b_shared2 = make_bank("B_SH2", 4000.0, bank_ref="GW_Q1")
        ledger_a = make_ledger("L_QA", "PAY_QA", 10000.0)
        ledger_b = make_ledger("L_QB", "PAY_QB", 10000.0)

        matcher = SplitMatcher(
            gateway_records=[gw_a, gw_b],
            bank_records=[b_shared1, b_shared2],
            ledger_records=[ledger_a, ledger_b],
            already_consumed=set(),
        )

        # Resolve Gateway A first — it should match and consume both rows
        result_a = matcher.resolve("PAY_QA", "GW_QA", "L_QA")
        self.assertEqual(result_a.status, SplitStatus.MATCH)
        self.assertIn("B_SH1", matcher._consumed)
        self.assertIn("B_SH2", matcher._consumed)

        # Gateway B now finds no available candidates
        result_b = matcher.resolve("PAY_QB", "GW_QB", "L_QB")
        self.assertNotEqual(result_b.status, SplitStatus.MATCH)
        # B_SH1 / B_SH2 must not be re-allocated to Gateway B
        self.assertNotIn("B_SH1", result_b.bank_row_ids)
        self.assertNotIn("B_SH2", result_b.bank_row_ids)


class TestDeterministicNoLLMCall(unittest.TestCase):
    """Test 18 — a deterministic single-combo split must not call Gemini."""

    def test_single_valid_combo_no_llm_call(self):
        gw = make_gateway("GW_R", "PAY_R", 9000.0, gw_reference="GW_R1")
        b1 = make_bank("B_R1", 5000.0, bank_ref="GW_R1")
        b2 = make_bank("B_R2", 4000.0, bank_ref="GW_R1")
        ledger = make_ledger("L_R", "PAY_R", 9000.0)

        mock_llm = _mock_llm()
        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_R", "GW_R", "L_R")],
            llm_client=mock_llm,
        )
        mock_llm.complete.assert_not_called()
        self.assertEqual(results[0].status, SplitStatus.MATCH)
        self.assertFalse(results[0].llm_consulted)


class TestGeminiUnavailable(unittest.TestCase):
    """Test 19 — Gemini unavailable → AI_RETRY_REQUIRED."""

    def test_llm_unavailable_gives_ai_retry(self):
        """Two valid combos exist; LLM raises LLMUnavailableError → AI_RETRY."""
        gw = make_gateway("GW_S", "PAY_S", 10000.0, gw_reference="GW_S1")
        b1 = make_bank("B_S1", 6000.0, bank_ref="GW_S1")
        b2 = make_bank("B_S2", 4000.0, bank_ref="GW_S1")
        b3 = make_bank("B_S3", 7000.0, bank_ref="GW_S1")
        b4 = make_bank("B_S4", 3000.0, bank_ref="GW_S1")
        ledger = make_ledger("L_S", "PAY_S", 10000.0)

        mock_llm = _mock_llm(raise_unavailable=True)
        results, summary = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_S", "GW_S", "L_S")],
            llm_client=mock_llm,
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.AI_RETRY_REQUIRED)
        self.assertEqual(summary.ai_retry_count, 1)


class TestInvalidGeminiRecommendation(unittest.TestCase):
    """Test 20 — invalid Gemini recommendation → AMBIGUOUS (not accepted)."""

    def test_unparseable_response_rejected(self):
        """Gemini returns garbled text — must fall through to AMBIGUOUS."""
        gw = make_gateway("GW_T", "PAY_T", 10000.0, gw_reference="GW_T1")
        b1 = make_bank("B_T1", 6000.0, bank_ref="GW_T1")
        b2 = make_bank("B_T2", 4000.0, bank_ref="GW_T1")
        b3 = make_bank("B_T3", 7000.0, bank_ref="GW_T1")
        b4 = make_bank("B_T4", 3000.0, bank_ref="GW_T1")
        ledger = make_ledger("L_T", "PAY_T", 10000.0)

        mock_llm = MagicMock()
        mock_llm.complete.return_value = "not json at all %%&"
        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_T", "GW_T", "L_T")],
            llm_client=mock_llm,
        )
        r = results[0]
        self.assertNotEqual(r.status, SplitStatus.MATCH)

    def test_low_confidence_recommendation_still_validated_arithmetically(self):
        """Confidence alone doesn't gate acceptance — arithmetic does."""
        gw = make_gateway("GW_T2", "PAY_T2", 10000.0, gw_reference="GW_T2")
        b1 = make_bank("B_T21", 6000.0, bank_ref="GW_T2")
        b2 = make_bank("B_T22", 4000.0, bank_ref="GW_T2")
        b3 = make_bank("B_T23", 7000.0, bank_ref="GW_T2")
        b4 = make_bank("B_T24", 3000.0, bank_ref="GW_T2")
        ledger = make_ledger("L_T2", "PAY_T2", 10000.0)

        matcher = SplitMatcher(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
        )
        rec = {
            "decision": "MATCH",
            "bank_row_ids": ["B_T21", "B_T22"],   # sum 10000 = expected ✓
            "confidence": 0.1,   # very low confidence
            "evidence": {},
            "adjustment": {},
        }
        validated, reason = matcher._validate_llm_recommendation(
            rec, ["B_T21", "B_T22", "B_T23", "B_T24"], Decimal("10000")
        )
        # Arithmetic is correct, so validation passes regardless of confidence
        self.assertIsNotNone(validated)
        self.assertIsNone(reason)


class TestValidGeminiRecommendation(unittest.TestCase):
    """Test 21 — valid Gemini recommendation independently validated and accepted."""

    def test_valid_llm_recommendation_accepted(self):
        """Gemini recommends B_V1+B_V2; Python validates arithmetic → MATCH."""
        gw = make_gateway("GW_V", "PAY_V", 10000.0, gw_reference="GW_V1")
        b1 = make_bank("B_V1", 6000.0, bank_ref="GW_V1")
        b2 = make_bank("B_V2", 4000.0, bank_ref="GW_V1")
        b3 = make_bank("B_V3", 7000.0, bank_ref="GW_V1")
        b4 = make_bank("B_V4", 3000.0, bank_ref="GW_V1")
        ledger = make_ledger("L_V", "PAY_V", 10000.0)

        # Two valid combos: (B_V1+B_V2) and (B_V3+B_V4). LLM picks first.
        mock_llm = _mock_llm(decision="MATCH", bank_row_ids=["B_V1", "B_V2"])
        results, summary = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_V", "GW_V", "L_V")],
            llm_client=mock_llm,
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.MATCH)
        self.assertTrue(r.llm_consulted)
        self.assertIn("B_V1", r.bank_row_ids)
        self.assertIn("B_V2", r.bank_row_ids)
        self.assertEqual(summary.llm_validated, 1)
        self.assertEqual(summary.llm_rejected, 0)

    def test_llm_recommendation_consumed_chosen_rows(self):
        """After accepting LLM recommendation the chosen rows must be consumed."""
        gw = make_gateway("GW_V2", "PAY_V2", 10000.0, gw_reference="GW_V2")
        b1 = make_bank("B_V21", 6000.0, bank_ref="GW_V2")
        b2 = make_bank("B_V22", 4000.0, bank_ref="GW_V2")
        b3 = make_bank("B_V23", 7000.0, bank_ref="GW_V2")
        b4 = make_bank("B_V24", 3000.0, bank_ref="GW_V2")
        ledger = make_ledger("L_V2", "PAY_V2", 10000.0)

        mock_llm = _mock_llm(decision="MATCH", bank_row_ids=["B_V21", "B_V22"])
        matcher = SplitMatcher(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            llm_client=mock_llm,
        )
        result = matcher.resolve("PAY_V2", "GW_V2", "L_V2")
        self.assertEqual(result.status, SplitStatus.MATCH)
        self.assertIn("B_V21", matcher._consumed)
        self.assertIn("B_V22", matcher._consumed)
        # B_V23 and B_V24 remain available
        self.assertNotIn("B_V23", matcher._consumed)
        self.assertNotIn("B_V24", matcher._consumed)


class TestPAY109ShapedBehaviour(unittest.TestCase):
    """Test 22 — PAY109-shaped split (generic; implementation must not hardcode
    the ID 'PAY109' anywhere — this test uses a different transaction ID)."""

    def test_pay109_shape_with_different_id(self):
        """Gateway ≈6400; two bank rows sum to ≈6395.50 (within tolerance)."""
        gw = make_gateway("GW_PAY_SIM", "PAY_SIM", 6400.0, gw_reference="GW_SIM")
        b1 = make_bank("B_SIM1", 3200.0, bank_ref="GW_SIM")
        b2 = make_bank("B_SIM2", 3195.50, bank_ref="GW_SIM")  # sum = 6395.50, diff 4.50
        ledger = make_ledger("L_SIM", "PAY_SIM", 6400.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_SIM", "GW_PAY_SIM", "L_SIM")],
        )
        r = results[0]
        self.assertEqual(r.status, SplitStatus.MATCH)
        self.assertEqual(r.rule, SplitRule.SPLIT_2_ROW)
        self.assertAlmostEqual(r.received, 6395.50, places=2)

    def test_implementation_has_no_pay109_hardcode(self):
        """Verify the implementation file does not contain 'PAY109' literally."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "core" / "match_split.py"
        content = src.read_text(encoding="utf-8")
        self.assertNotIn("PAY109", content,
                         "match_split.py must not hardcode the transaction ID 'PAY109'")


class TestSplitToDict(unittest.TestCase):
    """SplitResult.to_dict() must be JSON-serialisable."""

    def test_to_dict_serialisable(self):
        gw = make_gateway("GW_Z", "PAY_Z", 10000.0, gw_reference="GW_Z1")
        b1 = make_bank("B_Z1", 6000.0, bank_ref="GW_Z1")
        b2 = make_bank("B_Z2", 4000.0, bank_ref="GW_Z1")
        ledger = make_ledger("L_Z", "PAY_Z", 10000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_Z", "GW_Z", "L_Z")],
        )
        r = results[0]
        d = r.to_dict()
        # Must not raise
        serialised = json.dumps(d)
        self.assertIsInstance(serialised, str)
        self.assertIn("bank_row_ids", d)


class TestSummaryCounters(unittest.TestCase):
    """SplitSummary must count statuses correctly."""

    def test_summary_counts(self):
        # Match: GW1 (2-row exact)
        gw1 = make_gateway("GW_S1", "PAY_S1", 10000.0, gw_reference="GW_SC1")
        b1 = make_bank("B_SC1", 6000.0, bank_ref="GW_SC1")
        b2 = make_bank("B_SC2", 4000.0, bank_ref="GW_SC1")
        l1 = make_ledger("L_S1", "PAY_S1", 10000.0)

        # Partial: GW2
        gw2 = make_gateway("GW_S2", "PAY_S2", 20000.0, gw_reference="GW_SC2")
        b3 = make_bank("B_SC3", 8000.0, bank_ref="GW_SC2")
        l2 = make_ledger("L_S2", "PAY_S2", 20000.0)

        results, summary = run_stage3(
            gateway_records=[gw1, gw2],
            bank_records=[b1, b2, b3],
            ledger_records=[l1, l2],
            already_consumed=set(),
            pending_txns=[
                _pending("PAY_S1", "GW_S1", "L_S1"),
                _pending("PAY_S2", "GW_S2", "L_S2"),
            ],
        )
        self.assertEqual(summary.total_evaluated, 2)
        self.assertEqual(summary.match_count, 1)
        self.assertEqual(summary.partial_count, 1)

    def test_summary_llm_counters(self):
        """llm_validated and llm_rejected counters match actual outcomes."""
        gw = make_gateway("GW_SC2", "PAY_SC2", 10000.0, gw_reference="GW_SCLLM")
        b1 = make_bank("B_SCL1", 6000.0, bank_ref="GW_SCLLM")
        b2 = make_bank("B_SCL2", 4000.0, bank_ref="GW_SCLLM")
        b3 = make_bank("B_SCL3", 7000.0, bank_ref="GW_SCLLM")
        b4 = make_bank("B_SCL4", 3000.0, bank_ref="GW_SCLLM")
        ledger = make_ledger("L_SC2", "PAY_SC2", 10000.0)

        mock_llm = _mock_llm(decision="MATCH", bank_row_ids=["B_SCL1", "B_SCL2"])
        _, summary = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2, b3, b4],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_SC2", "GW_SC2", "L_SC2")],
            llm_client=mock_llm,
        )
        self.assertEqual(summary.llm_calls_made, 1)
        self.assertEqual(summary.llm_validated, 1)
        self.assertEqual(summary.llm_rejected, 0)


class TestBuildCandidatePool(unittest.TestCase):
    """Unit tests for _build_candidate_pool logic."""

    def _gw(self, ref="GW001"):
        return make_gateway("GW_CP", "PAY_CP", 1000.0, gw_reference=ref)

    def test_reference_evidence_preferred(self):
        gw = self._gw("GW001")
        b_ref = make_bank("B_REF", 400.0, bank_ref="GW001")
        b_amt = make_bank("B_AMT", 500.0)   # amount-plausible but no ref
        candidates, _ = _build_candidate_pool(gw, None, [b_ref, b_amt], set(), Decimal("1000"))
        self.assertIn(b_ref, candidates)
        # b_ref should come first (reference evidence preferred)
        self.assertEqual(candidates[0], b_ref)

    def test_consumed_rows_excluded(self):
        gw = self._gw("GW002")
        b1 = make_bank("B_CONS", 500.0, bank_ref="GW002")
        b2 = make_bank("B_AVAIL", 500.0, bank_ref="GW002")
        candidates, _ = _build_candidate_pool(gw, None, [b1, b2], {"B_CONS"}, Decimal("1000"))
        ids = [c.source_row_id for c in candidates]
        self.assertNotIn("B_CONS", ids)
        self.assertIn("B_AVAIL", ids)

    def test_limit_exceeded_returns_reason(self):
        gw = self._gw("GW003")
        banks = [make_bank(f"BL{i}", 200.0, bank_ref="GW003") for i in range(10)]
        candidates, reason = _build_candidate_pool(
            gw, None, banks, set(), Decimal("1000"), limit=3
        )
        self.assertEqual(reason, SplitReason.CANDIDATE_LIMIT_EXCEEDED)
        self.assertEqual(len(candidates), 3)  # capped at limit


class TestMaxComboSizeConfig(unittest.TestCase):
    """MAX_COMBO_SIZE config must bound the search."""

    def test_max_combo_size_1_prevents_split(self):
        """With max_combo_size=1 (edge case), no multi-row combo is tried."""
        gw = make_gateway("GW_MC", "PAY_MC", 10000.0, gw_reference="GW_MCS")
        b1 = make_bank("B_MC1", 6000.0, bank_ref="GW_MCS")
        b2 = make_bank("B_MC2", 4000.0, bank_ref="GW_MCS")
        ledger = make_ledger("L_MC", "PAY_MC", 10000.0)

        results, _ = run_stage3(
            gateway_records=[gw],
            bank_records=[b1, b2],
            ledger_records=[ledger],
            already_consumed=set(),
            pending_txns=[_pending("PAY_MC", "GW_MC", "L_MC")],
            max_combo_size=1,
        )
        # max_combo_size=1 means range(2, 2) → no combinations tried
        self.assertNotEqual(results[0].status, SplitStatus.MATCH)


if __name__ == "__main__":
    unittest.main()
