"""
Tests for core/qa_agent.py — Settlement Q&A Agent

Coverage required:
  1.  transaction lookup
  2.  status questions
  3.  evidence questions
  4.  human-review filtering
  5.  unresolved filtering
  6.  LLM-assisted rule filtering
  7.  unknown transaction
  8.  unsupported question
  9.  malformed/ambiguous question
  10. prevention of hallucinated transaction/evidence
  11. Gemini unavailable fallback
  12. Q&A cannot alter reconciliation results
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from copy import deepcopy

from core.match_exact import run_tier1, get_residue
from core.match_fuzzy import run_tier2
from core.match_llm import (
    run_tier3,
    LLMUnavailableError,
    STATUS_MATCH,
    STATUS_HUMAN_REVIEW,
    STATUS_UNRESOLVED,
    RULE_SPLIT_SETTLEMENT_SUM,
    RULE_TDS_LINKED_NET_AMOUNT,
    RULE_REFUND_LINKED_NET_AMOUNT,
    RULE_DESCRIPTION_LINKED_REFERENCE,
)
from core.qa_agent import (
    ReconciliationIndex,
    SettlementQAAgent,
    build_qa_agent,
    classify_intent,
    INTENT_LOOKUP,
    INTENT_STATUS,
    INTENT_WHY,
    INTENT_EVIDENCE,
    INTENT_FILTER_STATUS,
    INTENT_FILTER_RULE,
    INTENT_UNSUPPORTED,
    QAAnswer,
)


# ---------------------------------------------------------------------------
# Shared LLM stub — recommends the offered candidates (mirrors test_match_llm)
# ---------------------------------------------------------------------------

class GoodSplitSettlementLLM:
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [c["source_row_id"] for c in payload["candidate_bank_credits"]]
        return json.dumps({
            "decision": "MATCH",
            "bank_row_ids": ids,
            "confidence": 0.94,
            "rationale": "combined amounts within tolerance",
            "evidence": {"source": "candidate_sum"},
            "adjustment": {},
        })


# ---------------------------------------------------------------------------
# Module-level fixture: run the full pipeline once, reuse across tests
# ---------------------------------------------------------------------------

def _build_pipeline_results():
    r1, _, matcher = run_tier1(data_dir="data", return_matcher=True)
    residue1 = get_residue(r1)
    r2, _ = run_tier2(residue1, matcher)
    r3, _ = run_tier3(r2, matcher, llm_client=GoodSplitSettlementLLM())
    return r1, r2, r3


_R1, _R2, _R3 = _build_pipeline_results()


def _make_agent(**kwargs) -> SettlementQAAgent:
    """Build a Q&A agent from the shared pipeline results."""
    return build_qa_agent(_R1, _R2, _R3, **kwargs)


# ===========================================================================
# 1. Transaction lookup
# ===========================================================================

class TestTransactionLookup(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_lookup_returns_found_true_for_known_transaction(self):
        answer = self.agent.ask("What happened to PAY109?")
        self.assertTrue(answer.found)
        self.assertTrue(answer.supported)
        self.assertEqual(answer.intent, INTENT_LOOKUP)
        self.assertIn("PAY109", answer.transaction_ids)

    def test_lookup_includes_status_in_retrieved_data(self):
        answer = self.agent.ask("What happened to PAY109?")
        self.assertGreater(len(answer.retrieved_data), 0)
        self.assertIn("status", answer.retrieved_data[0])

    def test_lookup_explanation_contains_transaction_id(self):
        answer = self.agent.ask("What happened to PAY094?")
        self.assertIn("PAY094", answer.explanation)

    def test_lookup_explanation_contains_status(self):
        answer = self.agent.ask("What happened to PAY094?")
        # PAY094 is matched via REFUND_LINKED_NET_AMOUNT
        self.assertIn(STATUS_MATCH, answer.explanation)

    def test_lookup_tier1_matched_transaction(self):
        # PAY001 is a clean Tier 1 match — verify it is retrievable
        answer = self.agent.ask("What happened to PAY001?")
        self.assertTrue(answer.found)
        self.assertIn("PAY001", answer.transaction_ids)

    def test_lookup_case_insensitive_id(self):
        answer_upper = self.agent.ask("What happened to PAY109?")
        answer_lower = self.agent.ask("what happened to pay109?")
        self.assertEqual(answer_upper.transaction_ids, answer_lower.transaction_ids)
        self.assertEqual(answer_upper.found, answer_lower.found)


# ===========================================================================
# 2. Status questions
# ===========================================================================

class TestStatusQuestions(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_status_of_matched_transaction(self):
        answer = self.agent.ask("What is the reconciliation status of PAY109?")
        self.assertTrue(answer.found)
        self.assertEqual(answer.intent, INTENT_STATUS)
        self.assertIn(STATUS_MATCH, answer.explanation)

    def test_status_of_human_review_transaction(self):
        # PAY108 ends up HUMAN_REVIEW (symmetric evidence, no distinguishing field)
        answer = self.agent.ask("What is the status of PAY108?")
        self.assertTrue(answer.found)
        self.assertIn(STATUS_HUMAN_REVIEW, answer.explanation)

    def test_status_of_unresolved_transaction(self):
        # PAY105 is a true orphan → UNRESOLVED
        answer = self.agent.ask("Status of PAY105?")
        self.assertTrue(answer.found)
        self.assertIn(STATUS_UNRESOLVED, answer.explanation)

    def test_status_answer_contains_tier_info(self):
        answer = self.agent.ask("What is the reconciliation status of PAY001?")
        # TIER_1 result
        self.assertIn("TIER", answer.explanation)

    def test_status_no_llm_call(self):
        answer = self.agent.ask("What is the status of PAY109?")
        self.assertFalse(answer.llm_used)


# ===========================================================================
# 3. Evidence questions
# ===========================================================================

class TestEvidenceQuestions(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_evidence_answer_contains_amounts(self):
        answer = self.agent.ask("What evidence supports PAY109?")
        self.assertTrue(answer.found)
        self.assertEqual(answer.intent, INTENT_EVIDENCE)
        # PAY109 is a split settlement — evidence should include gateway_amount
        self.assertTrue(
            any("gateway_amount" in str(d) or "amount" in str(d)
                for d in answer.retrieved_data),
            "evidence data should contain amount fields"
        )

    def test_evidence_explanation_names_rule(self):
        answer = self.agent.ask("What evidence supports PAY109?")
        # Should mention split settlement rule
        self.assertIn("split", answer.explanation.lower())

    def test_evidence_for_tds_transaction_contains_tds_amount(self):
        answer = self.agent.ask("What evidence supports PAY098?")
        self.assertTrue(answer.found)
        self.assertTrue(
            any("tds" in str(d).lower() for d in answer.retrieved_data)
            or "tds" in answer.explanation.lower()
        )

    def test_evidence_for_refund_transaction_mentions_refund(self):
        answer = self.agent.ask("What evidence supports PAY094?")
        self.assertTrue(answer.found)
        ev_text = str(answer.retrieved_data) + answer.explanation
        self.assertTrue(
            "refund" in ev_text.lower() or "REFUND" in ev_text,
            "evidence should mention refund linkage"
        )

    def test_evidence_includes_source_row_ids(self):
        # matched_records in retrieved data should carry source row IDs
        answer = self.agent.ask("What evidence supports PAY001?")
        self.assertTrue(answer.found)
        data = answer.retrieved_data[0]
        matched = data.get("matched_records", {})
        self.assertTrue(
            any(v for v in matched.values() if v),
            "matched_records should contain at least one source row id"
        )

    def test_evidence_no_llm_call_when_llm_disabled(self):
        answer = self.agent.ask("What evidence supports PAY109?")
        self.assertFalse(answer.llm_used)


# ===========================================================================
# 4. Human-review filtering
# ===========================================================================

class TestHumanReviewFiltering(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_filter_returns_human_review_transactions(self):
        answer = self.agent.ask("Which transactions need human review?")
        self.assertTrue(answer.supported)
        self.assertEqual(answer.intent, INTENT_FILTER_STATUS)
        self.assertGreater(len(answer.transaction_ids), 0,
                           "there should be at least one HUMAN_REVIEW transaction")

    def test_filter_human_review_explanation_contains_count(self):
        answer = self.agent.ask("Which transactions need human review?")
        # Explanation should mention the count or list the IDs
        self.assertIn(str(len(answer.transaction_ids)), answer.explanation)

    def test_filter_human_review_all_have_correct_status(self):
        answer = self.agent.ask("Which transactions need human review?")
        index = ReconciliationIndex(_R1, _R2, _R3)
        for tid in answer.transaction_ids:
            entry = index.get(tid)
            self.assertIsNotNone(entry, f"{tid} not found in index")
            self.assertEqual(
                entry["data"]["status"],
                STATUS_HUMAN_REVIEW,
                f"{tid} should have HUMAN_REVIEW status"
            )

    def test_filter_phrasing_variants(self):
        for q in [
            "Which transactions need human review?",
            "Show all human review transactions",
            "List transactions that need manual review",
        ]:
            with self.subTest(q=q):
                answer = self.agent.ask(q)
                self.assertEqual(answer.intent, INTENT_FILTER_STATUS, f"intent wrong for: {q!r}")
                self.assertGreater(len(answer.transaction_ids), 0)


# ===========================================================================
# 5. Unresolved filtering
# ===========================================================================

class TestUnresolvedFiltering(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_filter_unresolved_returns_results(self):
        answer = self.agent.ask("Show me unresolved transactions.")
        self.assertTrue(answer.supported)
        self.assertEqual(answer.intent, INTENT_FILTER_STATUS)
        self.assertGreater(len(answer.transaction_ids), 0)

    def test_filter_unresolved_explanation_contains_count(self):
        answer = self.agent.ask("Show me unresolved transactions.")
        self.assertIn(str(len(answer.transaction_ids)), answer.explanation)

    def test_filter_unresolved_all_have_correct_status(self):
        answer = self.agent.ask("Show me unresolved transactions.")
        index = ReconciliationIndex(_R1, _R2, _R3)
        for tid in answer.transaction_ids:
            entry = index.get(tid)
            self.assertIsNotNone(entry)
            self.assertEqual(
                entry["data"]["status"],
                STATUS_UNRESOLVED,
                f"{tid} should be UNRESOLVED"
            )

    def test_orphan_pay105_is_in_unresolved_list(self):
        answer = self.agent.ask("Show me unresolved transactions.")
        self.assertIn("PAY105", answer.transaction_ids,
                      "PAY105 (true orphan) should appear in unresolved list")


# ===========================================================================
# 6. LLM-assisted rule filtering
# ===========================================================================

class TestLLMRuleFiltering(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_filter_split_settlement_returns_pay109(self):
        answer = self.agent.ask(
            "Which transactions were matched by the LLM-assisted split settlement rule?"
        )
        self.assertTrue(answer.supported)
        self.assertEqual(answer.intent, INTENT_FILTER_RULE)
        self.assertIn("PAY109", answer.transaction_ids)

    def test_filter_split_settlement_explanation_names_rule(self):
        answer = self.agent.ask(
            "Which transactions were matched by the split settlement rule?"
        )
        self.assertIn("split", answer.explanation.lower())

    def test_filter_refund_linked_returns_correct_transactions(self):
        answer = self.agent.ask(
            "Which transactions were matched by the refund-linked rule?"
        )
        self.assertEqual(answer.intent, INTENT_FILTER_RULE)
        self.assertGreater(len(answer.transaction_ids), 0)
        # Verify each result really uses that rule
        index = ReconciliationIndex(_R1, _R2, _R3)
        for tid in answer.transaction_ids:
            entry = index.get(tid)
            self.assertEqual(entry["data"]["rule"], RULE_REFUND_LINKED_NET_AMOUNT)

    def test_filter_tds_linked_returns_correct_transactions(self):
        answer = self.agent.ask(
            "Which transactions were matched by the TDS-linked rule?"
        )
        self.assertEqual(answer.intent, INTENT_FILTER_RULE)
        self.assertGreater(len(answer.transaction_ids), 0)
        index = ReconciliationIndex(_R1, _R2, _R3)
        for tid in answer.transaction_ids:
            entry = index.get(tid)
            self.assertEqual(entry["data"]["rule"], RULE_TDS_LINKED_NET_AMOUNT)

    def test_filter_no_llm_call(self):
        answer = self.agent.ask(
            "Which transactions were matched by the split settlement rule?"
        )
        self.assertFalse(answer.llm_used)


# ===========================================================================
# 6b. TDS/tax-line broader keyword coverage
# ===========================================================================

class TestTaxLineRuleFiltering(unittest.TestCase):
    """
    Verifies that product-style phrasings for TDS/tax-line questions
    are recognized as FILTER_RULE (TDS-linked net amount) — not UNSUPPORTED.
    """

    def setUp(self):
        self.agent = _make_agent()

    def test_how_many_tds_tax_line_issue(self):
        """The core product example that was previously UNSUPPORTED."""
        answer = self.agent.ask(
            "How many transactions had a TDS/tax-line issue?"
        )
        self.assertTrue(answer.supported)
        self.assertEqual(answer.intent, INTENT_FILTER_RULE)

    def test_tds_tax_line_returns_correct_rule_and_ids(self):
        answer = self.agent.ask(
            "How many transactions had a TDS/tax-line issue?"
        )
        self.assertGreater(len(answer.transaction_ids), 0)
        index = ReconciliationIndex(_R1, _R2, _R3)
        for tid in answer.transaction_ids:
            entry = index.get(tid)
            self.assertEqual(entry["data"]["rule"], RULE_TDS_LINKED_NET_AMOUNT)

    def test_tds_bare_keyword(self):
        answer = self.agent.ask("Show all TDS transactions")
        self.assertTrue(answer.supported)
        self.assertEqual(answer.intent, INTENT_FILTER_RULE)
        self.assertEqual(
            ReconciliationIndex(_R1, _R2, _R3).get(answer.transaction_ids[0])["data"]["rule"],
            RULE_TDS_LINKED_NET_AMOUNT,
        )

    def test_tax_line_mismatch_phrasing(self):
        answer = self.agent.ask(
            "Which transactions had a tax-line mismatch?"
        )
        self.assertTrue(answer.supported)
        self.assertEqual(answer.intent, INTENT_FILTER_RULE)

    def test_explanation_includes_count(self):
        answer = self.agent.ask(
            "How many transactions had a TDS/tax-line issue?"
        )
        self.assertIn(str(len(answer.transaction_ids)), answer.explanation)

    def test_no_llm_for_tds_filter(self):
        answer = self.agent.ask(
            "How many transactions had a TDS/tax-line issue?"
        )
        self.assertFalse(answer.llm_used)

    def test_classify_intent_tds_bare(self):
        """Unit-level: classify_intent recognizes bare TDS keyword."""
        intent, extras = classify_intent(
            "How many transactions had a TDS issue?"
        )
        self.assertEqual(intent, INTENT_FILTER_RULE)
        self.assertEqual(extras["rule"], RULE_TDS_LINKED_NET_AMOUNT)

    def test_classify_intent_tax_line(self):
        intent, extras = classify_intent("Show tax-line mismatches")
        self.assertEqual(intent, INTENT_FILTER_RULE)
        self.assertEqual(extras["rule"], RULE_TDS_LINKED_NET_AMOUNT)


# ===========================================================================
# 7. Unknown transaction
# ===========================================================================

class TestUnknownTransaction(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_unknown_transaction_returns_found_false(self):
        answer = self.agent.ask("What happened to PAY999?")
        self.assertFalse(answer.found)
        self.assertTrue(answer.supported)  # question is valid, txn just doesn't exist

    def test_unknown_transaction_explanation_says_not_found(self):
        answer = self.agent.ask("What happened to PAY999?")
        self.assertIn("not found", answer.explanation.lower())

    def test_unknown_transaction_has_empty_retrieved_data(self):
        answer = self.agent.ask("What happened to PAY999?")
        self.assertEqual(answer.retrieved_data, [])

    def test_unknown_transaction_no_llm_call(self):
        answer = self.agent.ask("What happened to PAY000?")
        self.assertFalse(answer.llm_used)

    def test_unknown_transaction_why_question(self):
        answer = self.agent.ask("Why is PAY999 matched?")
        self.assertFalse(answer.found)
        self.assertIn("not found", answer.explanation.lower())


# ===========================================================================
# 8. Unsupported question
# ===========================================================================

class TestUnsupportedQuestion(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_completely_off_topic_question(self):
        answer = self.agent.ask("What is the weather today?")
        self.assertFalse(answer.supported)
        self.assertEqual(answer.intent, INTENT_UNSUPPORTED)

    def test_reconciliation_request_is_unsupported(self):
        # The agent must never re-run the reconciliation pipeline
        answer = self.agent.ask("Please re-reconcile all transactions now.")
        self.assertFalse(answer.supported)
        self.assertEqual(answer.intent, INTENT_UNSUPPORTED)

    def test_modification_request_is_unsupported(self):
        answer = self.agent.ask("Change the status of PAY109 to UNRESOLVED.")
        # Either unsupported OR found=True but no mutation — see test 12
        # The safest expectation is that the agent does NOT modify any result
        index_before = ReconciliationIndex(_R1, _R2, _R3)
        entry_before = index_before.get("PAY109")
        answer = self.agent.ask("Change the status of PAY109 to UNRESOLVED.")
        index_after = ReconciliationIndex(_R1, _R2, _R3)
        entry_after = index_after.get("PAY109")
        self.assertEqual(
            entry_before["data"]["status"],
            entry_after["data"]["status"],
            "Q&A must never alter the reconciliation result"
        )

    def test_unsupported_explanation_lists_supported_types(self):
        answer = self.agent.ask("What is the weather today?")
        self.assertIn("supported", answer.explanation.lower())

    def test_empty_question_is_unsupported(self):
        answer = self.agent.ask("")
        self.assertFalse(answer.supported)

    def test_whitespace_only_question_is_unsupported(self):
        answer = self.agent.ask("   ")
        self.assertFalse(answer.supported)


# ===========================================================================
# 9. Malformed / ambiguous question
# ===========================================================================

class TestMalformedQuestion(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_question_with_no_transaction_id_but_transaction_framing(self):
        # "What happened?" with no ID — should be UNSUPPORTED, not a crash
        answer = self.agent.ask("What happened?")
        self.assertIsInstance(answer, QAAnswer)
        self.assertFalse(answer.supported)

    def test_question_with_partial_id_does_not_crash(self):
        answer = self.agent.ask("PAY")
        self.assertIsInstance(answer, QAAnswer)

    def test_question_with_multiple_ids_picks_first(self):
        # If multiple IDs appear, the agent picks the first — no crash.
        answer = self.agent.ask("Compare PAY109 and PAY098")
        self.assertIsInstance(answer, QAAnswer)
        # At minimum the agent should handle it without raising
        self.assertIsNotNone(answer.explanation)

    def test_gibberish_question_does_not_crash(self):
        answer = self.agent.ask("xyzzy blorph quux !!!")
        self.assertIsInstance(answer, QAAnswer)
        self.assertFalse(answer.supported)

    def test_very_long_question_does_not_crash(self):
        long_q = "What happened to PAY109? " * 200
        answer = self.agent.ask(long_q)
        self.assertIsInstance(answer, QAAnswer)
        self.assertTrue(answer.found)


# ===========================================================================
# 10. Prevention of hallucinated transaction / evidence
# ===========================================================================

class TestNoHallucination(unittest.TestCase):

    def setUp(self):
        self.agent = _make_agent()

    def test_invented_transaction_id_returns_not_found(self):
        # A transaction that was never in the pipeline must never be fabricated
        answer = self.agent.ask("What happened to PAY999?")
        self.assertFalse(answer.found)
        self.assertEqual(answer.retrieved_data, [])

    def test_answer_for_real_transaction_contains_no_extra_ids(self):
        answer = self.agent.ask("What happened to PAY109?")
        # Only PAY109 should appear in transaction_ids
        self.assertEqual(answer.transaction_ids, ["PAY109"])

    def test_evidence_data_matches_pipeline_output(self):
        """
        The evidence returned by the Q&A agent must be identical to what
        the reconciliation pipeline produced — not invented or augmented.
        """
        # Build a direct index from the pipeline results
        index = ReconciliationIndex(_R1, _R2, _R3)
        expected_entry = index.get("PAY109")
        self.assertIsNotNone(expected_entry)

        answer = self.agent.ask("What evidence supports PAY109?")
        self.assertTrue(answer.found)
        self.assertGreater(len(answer.retrieved_data), 0)

        # The evidence field in retrieved_data must equal the pipeline's evidence
        qa_evidence = answer.retrieved_data[0].get("evidence", {})
        pipeline_evidence = expected_entry["data"].get("evidence", {})
        self.assertEqual(
            qa_evidence, pipeline_evidence,
            "Q&A evidence must exactly match pipeline evidence — no invention"
        )

    def test_filter_returns_only_pipeline_known_ids(self):
        """
        Every transaction ID in a filter answer must exist in the pipeline index.
        """
        index = ReconciliationIndex(_R1, _R2, _R3)
        known_ids = set(index.all_transaction_ids())

        answer = self.agent.ask("Show me unresolved transactions.")
        for tid in answer.transaction_ids:
            self.assertIn(
                tid, known_ids,
                f"{tid} appeared in filter answer but is not in the pipeline index"
            )

    def test_status_answer_reflects_pipeline_status_exactly(self):
        """The status reported by the Q&A agent must match the pipeline exactly."""
        index = ReconciliationIndex(_R1, _R2, _R3)
        for txn_id in ["PAY109", "PAY108", "PAY105", "PAY001"]:
            with self.subTest(txn_id=txn_id):
                entry = index.get(txn_id)
                if entry is None:
                    continue
                expected_status = entry["data"]["status"]
                answer = self.agent.ask(f"What is the status of {txn_id}?")
                self.assertTrue(answer.found)
                self.assertIn(
                    expected_status,
                    answer.explanation,
                    f"Status for {txn_id} should be {expected_status}"
                )


# ===========================================================================
# 11. Gemini unavailable fallback
# ===========================================================================

class TestGeminiUnavailableFallback(unittest.TestCase):

    def test_agent_works_without_any_llm_client(self):
        agent = build_qa_agent(_R1, _R2, _R3, llm_client=None)
        answer = agent.ask("What happened to PAY109?")
        self.assertTrue(answer.found)
        self.assertFalse(answer.llm_used)
        self.assertIsNotNone(answer.explanation)

    def test_agent_falls_back_when_gemini_raises_llm_unavailable(self):
        """
        When use_llm_for_explanations=True but the client raises
        LLMUnavailableError, the agent returns a template explanation and
        sets llm_unavailable=True.
        """
        class FailingLLM:
            def complete(self, system, user):
                raise LLMUnavailableError("simulated outage")

        agent = build_qa_agent(
            _R1, _R2, _R3,
            llm_client=FailingLLM(),
            use_llm_for_explanations=True,
        )
        answer = agent.ask("What happened to PAY109?")
        self.assertTrue(answer.found)
        self.assertFalse(answer.llm_used)
        self.assertTrue(answer.llm_unavailable)
        # Must still return a meaningful template explanation
        self.assertIn("PAY109", answer.explanation)

    def test_agent_uses_llm_when_available_and_enabled(self):
        """When a working LLM client is provided, llm_used=True on lookup questions."""
        class ProseOnlyLLM:
            def complete(self, system, user):
                return "This transaction was reconciled using a split settlement rule."

        agent = build_qa_agent(
            _R1, _R2, _R3,
            llm_client=ProseOnlyLLM(),
            use_llm_for_explanations=True,
        )
        answer = agent.ask("What happened to PAY109?")
        self.assertTrue(answer.found)
        self.assertTrue(answer.llm_used)
        self.assertIn("settlement", answer.explanation.lower())

    def test_filter_answers_never_use_llm(self):
        """Filter questions are always answered deterministically — no LLM."""
        class ProseOnlyLLM:
            def complete(self, system, user):
                return "Should never be called for filter questions."

        agent = build_qa_agent(
            _R1, _R2, _R3,
            llm_client=ProseOnlyLLM(),
            use_llm_for_explanations=True,
        )
        for q in [
            "Which transactions need human review?",
            "Show me unresolved transactions.",
            "Which transactions were matched by the split settlement rule?",
        ]:
            with self.subTest(q=q):
                answer = agent.ask(q)
                self.assertFalse(answer.llm_used, f"LLM was incorrectly used for: {q!r}")

    def test_missing_api_key_env_does_not_crash_agent_construction(self):
        """Auto-selecting Gemini from env with no key set must not raise at init."""
        with patch.dict("os.environ", {}, clear=True):
            # pop both keys so auto-selection finds nothing
            import os
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("LLM_PROVIDER", None)
            # Should not raise
            agent = SettlementQAAgent(
                ReconciliationIndex(_R1, _R2, _R3),
                use_llm_for_explanations=True,
            )
            answer = agent.ask("What happened to PAY109?")
            self.assertTrue(answer.found)
            self.assertFalse(answer.llm_used)


# ===========================================================================
# 12. Q&A cannot alter reconciliation results
# ===========================================================================

class TestReadOnlySafety(unittest.TestCase):

    def _snapshot_results(self):
        """Serialize all results to dicts for comparison (deep equality)."""
        return {
            "t1": [r.to_dict() for r in _R1],
            "t2": [r.to_dict() for r in _R2],
            "t3": [r.to_dict() for r in _R3],
        }

    def test_ask_does_not_modify_tier1_results(self):
        before = self._snapshot_results()
        agent = _make_agent()
        for q in [
            "What happened to PAY001?",
            "Which transactions need human review?",
            "Show me unresolved transactions.",
            "What is the status of PAY109?",
            "Why is PAY109 matched?",
        ]:
            agent.ask(q)
        after = self._snapshot_results()
        self.assertEqual(before["t1"], after["t1"],
                         "Tier 1 results were modified by Q&A agent")

    def test_ask_does_not_modify_tier2_results(self):
        before = self._snapshot_results()
        agent = _make_agent()
        agent.ask("What evidence supports PAY071?")
        after = self._snapshot_results()
        self.assertEqual(before["t2"], after["t2"],
                         "Tier 2 results were modified by Q&A agent")

    def test_ask_does_not_modify_tier3_results(self):
        before = self._snapshot_results()
        agent = _make_agent()
        agent.ask("What happened to PAY109?")
        after = self._snapshot_results()
        self.assertEqual(before["t3"], after["t3"],
                         "Tier 3 results were modified by Q&A agent")

    def test_repeated_asks_produce_identical_answers(self):
        """
        Asking the same question twice must produce the same answer —
        confirms the agent has no mutable state that drifts.
        """
        agent = _make_agent()
        a1 = agent.ask("What happened to PAY109?")
        a2 = agent.ask("What happened to PAY109?")
        self.assertEqual(a1.found, a2.found)
        self.assertEqual(a1.transaction_ids, a2.transaction_ids)
        self.assertEqual(a1.intent, a2.intent)
        # Status in retrieved data must be stable
        self.assertEqual(
            a1.retrieved_data[0]["status"],
            a2.retrieved_data[0]["status"],
        )

    def test_index_build_does_not_mutate_input_lists(self):
        """
        Building ReconciliationIndex must not mutate the lists it receives.
        """
        t1_ids_before = [r.transaction_id for r in _R1]
        t3_statuses_before = [r.status for r in _R3]

        _ = ReconciliationIndex(_R1, _R2, _R3)

        t1_ids_after = [r.transaction_id for r in _R1]
        t3_statuses_after = [r.status for r in _R3]

        self.assertEqual(t1_ids_before, t1_ids_after)
        self.assertEqual(t3_statuses_before, t3_statuses_after)


# ===========================================================================
# Intent classifier unit tests (fast, no pipeline needed)
# ===========================================================================

class TestIntentClassifier(unittest.TestCase):

    def test_lookup_intent(self):
        intent, extras = classify_intent("What happened to PAY109?")
        self.assertEqual(intent, INTENT_LOOKUP)
        self.assertEqual(extras["transaction_id"], "PAY109")

    def test_why_intent(self):
        intent, extras = classify_intent("Why is PAY109 matched?")
        self.assertEqual(intent, INTENT_WHY)
        self.assertEqual(extras["transaction_id"], "PAY109")

    def test_evidence_intent(self):
        intent, extras = classify_intent("What evidence supports PAY109?")
        self.assertEqual(intent, INTENT_EVIDENCE)
        self.assertEqual(extras["transaction_id"], "PAY109")

    def test_status_intent(self):
        intent, extras = classify_intent("What is the reconciliation status of PAY109?")
        self.assertEqual(intent, INTENT_STATUS)
        self.assertEqual(extras["transaction_id"], "PAY109")

    def test_filter_human_review_intent(self):
        intent, extras = classify_intent("Which transactions need human review?")
        self.assertEqual(intent, INTENT_FILTER_STATUS)
        self.assertEqual(extras["status"], STATUS_HUMAN_REVIEW)

    def test_filter_unresolved_intent(self):
        intent, extras = classify_intent("Show me unresolved transactions.")
        self.assertEqual(intent, INTENT_FILTER_STATUS)
        self.assertEqual(extras["status"], STATUS_UNRESOLVED)

    def test_filter_split_settlement_rule(self):
        intent, extras = classify_intent(
            "Which transactions were matched by the LLM-assisted split settlement rule?"
        )
        self.assertEqual(intent, INTENT_FILTER_RULE)
        self.assertEqual(extras["rule"], RULE_SPLIT_SETTLEMENT_SUM)

    def test_unsupported_intent(self):
        intent, _ = classify_intent("What is the weather today?")
        self.assertEqual(intent, INTENT_UNSUPPORTED)

    def test_empty_string_is_unsupported(self):
        intent, _ = classify_intent("")
        self.assertEqual(intent, INTENT_UNSUPPORTED)


# ===========================================================================
# ReconciliationIndex unit tests
# ===========================================================================

class TestReconciliationIndex(unittest.TestCase):

    def setUp(self):
        self.index = ReconciliationIndex(_R1, _R2, _R3)

    def test_get_returns_none_for_unknown_id(self):
        self.assertIsNone(self.index.get("PAY999"))

    def test_get_returns_dict_for_known_id(self):
        entry = self.index.get("PAY001")
        self.assertIsNotNone(entry)
        self.assertIn("tier", entry)
        self.assertIn("data", entry)

    def test_tier3_takes_priority_over_tier1(self):
        # PAY109 is processed by Tier 3 — its authoritative tier must be TIER_3
        entry = self.index.get("PAY109")
        self.assertEqual(entry["tier"], "TIER_3")

    def test_tier1_used_for_clean_matches_not_in_residue(self):
        # PAY001 was matched at Tier 1 and never entered Tier 2 residue
        entry = self.index.get("PAY001")
        self.assertIsNotNone(entry)

    def test_filter_by_status_returns_only_matching(self):
        hr_entries = self.index.filter_by_status(STATUS_HUMAN_REVIEW)
        for e in hr_entries:
            self.assertEqual(e["status"], STATUS_HUMAN_REVIEW)

    def test_filter_by_rule_returns_only_matching(self):
        split_entries = self.index.filter_by_rule(RULE_SPLIT_SETTLEMENT_SUM)
        for e in split_entries:
            self.assertEqual(e["rule"], RULE_SPLIT_SETTLEMENT_SUM)

    def test_summary_counts_include_all_known_statuses(self):
        counts = self.index.summary_counts()
        # Every entry must be accounted for
        total = sum(counts.values())
        self.assertEqual(total, len(self.index.all_transaction_ids()))


if __name__ == "__main__":
    unittest.main()
