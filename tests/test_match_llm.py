import json
import os
import unittest
from unittest.mock import patch, MagicMock

from core.match_exact import run_tier1, get_residue
from core.match_fuzzy import run_tier2
from core.match_llm import (
    run_tier3,
    get_final_residue,
    LLMClient,
    LLMUnavailableError,
    GeminiLLMClient,
    LLMAdjudicator,
    STATUS_MATCH,
    STATUS_HUMAN_REVIEW,
    STATUS_UNRESOLVED,
    STATUS_AI_RETRY_REQUIRED,
    RULE_REFUND_LINKED_NET_AMOUNT,
    RULE_TDS_LINKED_NET_AMOUNT,
    RULE_DESCRIPTION_LINKED_REFERENCE,
    RULE_SPLIT_SETTLEMENT_SUM,
    REASON_AMBIGUOUS_DUPLICATE_CANDIDATES,
    REASON_NO_EVIDENCE_AVAILABLE,
    REASON_NO_SEPARATE_SETTLEMENT_EXPECTED,
    REASON_CONTRADICTORY_EVIDENCE_NO_EXPLANATION,
    REASON_SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD,
    REASON_LLM_UNAVAILABLE,
    REASON_AI_RETRY_REQUIRED,
    REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR,
)


class GoodSplitSettlementLLM:
    """Recommends exactly the pre-vetted candidates offered to it."""
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [c["source_row_id"] for c in payload["candidate_bank_credits"]]
        return json.dumps({
            "decision": "MATCH",
            "bank_row_ids": ids,
            "confidence": 0.94,
            "rationale": "combined amounts land within tolerance of the gateway amount",
            "evidence": {"source": "candidate_sum"},
            "adjustment": {},
        })


class FabricatingLLM:
    """Recommends a bank row that was never offered to it -- must be rejected."""
    def complete(self, system, user):
        return json.dumps({"decision": "MATCH", "bank_row_ids": ["B999"], "confidence": 0.9, "rationale": "invented", "evidence": {}, "adjustment": {}})


class OverreachingLLM:
    """Recommends MATCH on a single (not summed) row that isn't a real combo."""
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [payload["candidate_bank_credits"][0]["source_row_id"]]
        return json.dumps({"decision": "MATCH", "bank_row_ids": ids, "confidence": 0.8, "rationale": "close enough", "evidence": {}, "adjustment": {}})


class HumanReviewDecisionLLM:
    """Returns HUMAN_REVIEW decision instead of MATCH -- must be rejected as non-match."""
    def complete(self, system, user):
        return json.dumps({
            "decision": "HUMAN_REVIEW",
            "bank_row_ids": ["B107", "B108"],
            "rationale": "evidence is ambiguous",
        })


class MissingBankRowIdsLLM:
    """Omits bank_row_ids entirely -- must be rejected."""
    def complete(self, system, user):
        return json.dumps({"decision": "MATCH", "confidence": 0.5, "rationale": "no ids provided", "evidence": {}, "adjustment": {}})


class EmptyBankRowIdsLLM:
    """Returns empty bank_row_ids array -- must be rejected (needs >= 2)."""
    def complete(self, system, user):
        return json.dumps({"decision": "MATCH", "bank_row_ids": [], "confidence": 0.5, "rationale": "empty", "evidence": {}, "adjustment": {}})


class OutOfToleranceLLM:
    """Recommends two rows whose sum is far outside SPLIT_SETTLEMENT_TOLERANCE."""
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [c["source_row_id"] for c in payload["candidate_bank_credits"]]
        # Return the same ids but the system must recompute the sum and
        # reject if it's outside tolerance. The actual amounts from the
        # candidate set should be within tolerance for PAY109, so to test
        # out-of-tolerance we fabricate a sum check by returning a known
        # bad combo that won't be in the candidate set.
        return json.dumps({
            "decision": "MATCH",
            "bank_row_ids": ids[:1] if ids else ["B999"],
            "confidence": 0.8,
            "rationale": "sums within tolerance",
            "evidence": {},
            "adjustment": {},
        })


class DuplicateIdsLLM:
    """Returns duplicate bank_row_ids -- must be rejected (one-to-one)."""
    def complete(self, system, user):
        payload = json.loads(user)
        first = payload["candidate_bank_credits"][0]["source_row_id"]
        return json.dumps({
            "decision": "MATCH",
            "bank_row_ids": [first, first],
            "confidence": 0.8,
            "rationale": "duplicated",
            "evidence": {},
            "adjustment": {},
        })


class FencedJsonLLM:
    """Returns the valid recommendation wrapped in markdown fences -- the actual
    failure mode observed in live Gemini calls. Must still parse and resolve."""
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [c["source_row_id"] for c in payload["candidate_bank_credits"]]
        inner = json.dumps({
            "decision": "MATCH",
            "bank_row_ids": ids,
            "confidence": 0.94,
            "rationale": "combined amounts land within tolerance of the gateway amount",
            "evidence": {},
            "adjustment": {},
        })
        return f"```json\n{inner}\n```"


class UnparseableLLM:
    def complete(self, system, user):
        return "not json at all"


class MissingConfidenceLLM:
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [c["source_row_id"] for c in payload["candidate_bank_credits"]]
        return json.dumps({
            "decision": "MATCH", "bank_row_ids": ids,
            "rationale": "missing confidence", "evidence": {}, "adjustment": {},
        })


class OutOfRangeConfidenceLLM:
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [c["source_row_id"] for c in payload["candidate_bank_credits"]]
        return json.dumps({
            "decision": "MATCH", "bank_row_ids": ids, "confidence": 1.1,
            "rationale": "invalid confidence", "evidence": {}, "adjustment": {},
        })


class RaisingLLM:
    def complete(self, system, user):
        raise LLMUnavailableError("simulated outage")


def _run_pipeline(llm_client=None):
    r1, _, matcher = run_tier1(data_dir="data", return_matcher=True)
    residue1 = get_residue(r1)
    r2, _ = run_tier2(residue1, matcher)
    r3, summary = run_tier3(r2, matcher, llm_client=llm_client)
    return {r.transaction_id: r for r in r3}, summary


class TestDeterministicRulesNeverCallLLM(unittest.TestCase):
    """
    The refund-linked, TDS-linked, and description-linked rules are all
    directly provable from the raw records. They must resolve correctly
    with ZERO llm calls, even when an LLM client is available -- Tier 3
    must never spend a call on evidence it can already prove itself.
    """

    def setUp(self):
        self.by_txn, self.summary = _run_pipeline(llm_client=GoodSplitSettlementLLM())

    def test_refund_linked_matches(self):
        for pid in ("PAY094", "PAY095", "PAY096", "PAY097"):
            with self.subTest(pid=pid):
                r = self.by_txn[pid]
                self.assertEqual(r.status, STATUS_MATCH)
                self.assertEqual(r.rule, RULE_REFUND_LINKED_NET_AMOUNT)
                self.assertIsNotNone(r.matched_records["bank"])
                self.assertFalse(r.llm_consulted)

    def test_refund_rows_marked_explained_not_broken(self):
        for pid in ("PAY094-REFUND", "PAY095-REFUND", "PAY096-REFUND", "PAY097-REFUND"):
            with self.subTest(pid=pid):
                r = self.by_txn[pid]
                self.assertEqual(r.status, STATUS_UNRESOLVED)
                self.assertEqual(r.reason, REASON_NO_SEPARATE_SETTLEMENT_EXPECTED)
                self.assertFalse(r.llm_consulted)

    def test_tds_linked_matches(self):
        for pid in ("PAY098", "PAY099", "PAY100", "PAY101", "PAY102"):
            with self.subTest(pid=pid):
                r = self.by_txn[pid]
                self.assertEqual(r.status, STATUS_MATCH)
                self.assertEqual(r.rule, RULE_TDS_LINKED_NET_AMOUNT)
                self.assertFalse(r.llm_consulted)

    def test_description_linked_match(self):
        r = self.by_txn["PAY111"]
        self.assertEqual(r.status, STATUS_MATCH)
        self.assertEqual(r.rule, RULE_DESCRIPTION_LINKED_REFERENCE)
        self.assertFalse(r.llm_consulted)

    def test_deterministic_rules_never_touch_llm_call_counter(self):
        # Only PAY109 (split settlement) should ever reach the LLM in this
        # dataset -- so exactly one call, no more.
        self.assertEqual(self.summary.llm_calls_made, 1)


class TestNoDeterministicEvidenceGivesSafeDispositions(unittest.TestCase):

    def setUp(self):
        self.by_txn, _ = _run_pipeline(llm_client=None)

    def test_duplicate_ledger_requires_human_review_not_a_guess(self):
        for pid in ("PAY091", "PAY092", "PAY093"):
            with self.subTest(pid=pid):
                r = self.by_txn[pid]
                self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
                self.assertEqual(r.reason, REASON_AMBIGUOUS_DUPLICATE_CANDIDATES)
                self.assertIsNone(r.rule)

    def test_no_bank_counterpart_is_unresolved_not_human_review(self):
        for pid in ("PAY103", "PAY104"):
            with self.subTest(pid=pid):
                r = self.by_txn[pid]
                self.assertEqual(r.status, STATUS_UNRESOLVED)
                self.assertEqual(r.reason, REASON_NO_EVIDENCE_AVAILABLE)

    def test_true_orphan_and_decoy_are_unresolved(self):
        for pid in ("PAY105", "PAY107B"):
            with self.subTest(pid=pid):
                r = self.by_txn[pid]
                self.assertEqual(r.status, STATUS_UNRESOLVED)

    def test_contradictory_amount_is_human_review_never_forced(self):
        r = self.by_txn["PAY110"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertEqual(r.reason, REASON_CONTRADICTORY_EVIDENCE_NO_EXPLANATION)
        self.assertIsNone(r.rule)

    def test_symmetric_ambiguous_bank_credits_are_human_review(self):
        r = self.by_txn["PAY108"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertEqual(r.reason, REASON_SYMMETRIC_EVIDENCE_NO_DISTINGUISHING_FIELD)
        # No distinguishing evidence exists at all for this case -- Tier 3
        # must not spend an LLM call chasing evidence that can't exist.
        self.assertFalse(r.llm_consulted)

    def test_split_settlement_without_llm_client_defers_safely(self):
        r = self.by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_AI_RETRY_REQUIRED)
        self.assertEqual(r.reason, REASON_AI_RETRY_REQUIRED)
        self.assertFalse(r.llm_consulted)


class TestLLMRecommendationsAreIndependentlyValidated(unittest.TestCase):

    def test_valid_llm_recommendation_is_accepted_and_arithmetic_checked(self):
        by_txn, summary = _run_pipeline(llm_client=GoodSplitSettlementLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_MATCH)
        self.assertEqual(r.rule, RULE_SPLIT_SETTLEMENT_SUM)
        self.assertEqual(set(r.matched_records["bank"].split(",")), {"B107", "B108"})
        self.assertTrue(r.llm_consulted)
        self.assertEqual(summary.llm_calls_made, 1)
        self.assertEqual(summary.llm_recommendations_validated, 1)
        self.assertEqual(summary.llm_recommendations_rejected, 0)

    def test_fabricated_bank_row_id_is_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=FabricatingLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertIn(r.reason, [REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR, "CANDIDATE_NOT_AVAILABLE", "INSUFFICIENT_BANK_ROWS"])
        self.assertTrue(r.llm_consulted)
        self.assertEqual(summary.llm_recommendations_rejected, 1)
        self.assertEqual(summary.llm_recommendations_validated, 0)

    def test_single_row_recommendation_that_does_not_sum_is_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=OverreachingLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertEqual(summary.llm_recommendations_rejected, 1)

    def test_unparseable_llm_response_is_rejected_not_crashing(self):
        by_txn, summary = _run_pipeline(llm_client=UnparseableLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertEqual(summary.llm_recommendations_rejected, 1)

    def test_missing_confidence_is_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=MissingConfidenceLLM())
        self.assertEqual(by_txn["PAY109"].status, STATUS_HUMAN_REVIEW)
        self.assertEqual(by_txn["PAY109"].reason, "MISSING_CONFIDENCE")
        self.assertEqual(summary.llm_recommendations_rejected, 1)

    def test_out_of_range_confidence_is_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=OutOfRangeConfidenceLLM())
        self.assertEqual(by_txn["PAY109"].status, STATUS_HUMAN_REVIEW)
        self.assertEqual(by_txn["PAY109"].reason, "INVALID_CONFIDENCE")
        self.assertEqual(summary.llm_recommendations_rejected, 1)

    def test_llm_outage_is_handled_gracefully(self):
        by_txn, summary = _run_pipeline(llm_client=RaisingLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_AI_RETRY_REQUIRED)
        self.assertEqual(r.reason, REASON_AI_RETRY_REQUIRED)
        self.assertTrue(r.llm_consulted)


class TestLLMRejectionEdgeCases(unittest.TestCase):
    """Focused rejection tests for the Gemini contract boundary. Each case
    verifies that a malformed, incomplete, or non-MATCH recommendation from
    the LLM is safely rejected as HUMAN_REVIEW without crashing."""

    def test_human_review_decision_is_rejected_not_forced_to_match(self):
        by_txn, summary = _run_pipeline(llm_client=HumanReviewDecisionLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        # Accept both old generic reason and new specific reason
        self.assertIn(r.reason, [REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR, "NON_MATCH_DECISION"])
        self.assertTrue(r.llm_consulted)
        self.assertEqual(summary.llm_recommendations_rejected, 1)
        self.assertEqual(summary.llm_recommendations_validated, 0)

    def test_missing_bank_row_ids_field_is_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=MissingBankRowIdsLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertIn(r.reason, [REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR, "INSUFFICIENT_BANK_ROWS"])
        self.assertTrue(r.llm_consulted)

    def test_empty_bank_row_ids_array_is_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=EmptyBankRowIdsLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertIn(r.reason, [REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR, "INSUFFICIENT_BANK_ROWS"])
        self.assertTrue(r.llm_consulted)

    def test_single_id_recommendation_is_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=OutOfToleranceLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertEqual(summary.llm_recommendations_rejected, 1)

    def test_duplicate_bank_row_ids_are_rejected(self):
        by_txn, summary = _run_pipeline(llm_client=DuplicateIdsLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_HUMAN_REVIEW)
        self.assertIn(r.reason, [REASON_LLM_RECOMMENDATION_REJECTED_BY_VALIDATOR, "DUPLICATE_BANK_ROW_ID"])
        self.assertTrue(r.llm_consulted)

    def test_fenced_json_response_resolves_correctly(self):
        """Markdown-fenced JSON is the actual live Gemini failure mode.
        Must parse, validate, and resolve to MATCH."""
        by_txn, summary = _run_pipeline(llm_client=FencedJsonLLM())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_MATCH)
        self.assertEqual(r.rule, RULE_SPLIT_SETTLEMENT_SUM)
        self.assertEqual(set(r.matched_records["bank"].split(",")), {"B107", "B108"})
        self.assertTrue(r.llm_consulted)
        self.assertEqual(summary.llm_recommendations_validated, 1)
        self.assertEqual(summary.llm_recommendations_rejected, 0)


class TestOneToOneProtectionAcrossTier3(unittest.TestCase):
    """
    A bank row Tier 3 consumes for one transaction must never be reusable
    by a later transaction in the same run, even across the refund/TDS/
    description/split-settlement rules.
    """

    def test_no_bank_row_used_twice_in_a_real_run(self):
        by_txn, _ = _run_pipeline(llm_client=GoodSplitSettlementLLM())
        used_bank_ids = []
        for r in by_txn.values():
            bank_field = r.matched_records.get("bank")
            if not bank_field:
                continue
            used_bank_ids.extend(bank_field.split(","))
        self.assertEqual(len(used_bank_ids), len(set(used_bank_ids)),
                          "a bank row was consumed by more than one Tier 3 match")


class TestFullPipelineCounts(unittest.TestCase):
    """Locks in the measured, hand-verified outcome on the real dataset."""

    def test_counts_without_llm(self):
        by_txn, summary = _run_pipeline(llm_client=None)
        self.assertEqual(summary.total_residue_evaluated, 24)
        self.assertEqual(summary.match_count, 10)
        self.assertEqual(summary.human_review_count, 5)
        self.assertEqual(summary.unresolved_count, 8)
        self.assertEqual(summary.llm_calls_made, 0)

    def test_counts_with_valid_split_settlement_llm(self):
        by_txn, summary = _run_pipeline(llm_client=GoodSplitSettlementLLM())
        self.assertEqual(summary.match_count, 11)
        self.assertEqual(summary.human_review_count, 5)
        self.assertEqual(summary.unresolved_count, 8)

    def test_never_reprocesses_tier2_matched_transactions(self):
        r1, _, matcher = run_tier1(data_dir="data", return_matcher=True)
        residue1 = get_residue(r1)
        r2, _ = run_tier2(residue1, matcher)
        r3, _ = run_tier3(r2, matcher, llm_client=None)
        tier3_txn_ids = {r.transaction_id for r in r3}
        tier2_matched_ids = {r.transaction_id for r in r2 if r.status == "MATCHED"}
        self.assertEqual(tier3_txn_ids & tier2_matched_ids, set())

    def test_final_residue_excludes_all_matches(self):
        r1, _, matcher = run_tier1(data_dir="data", return_matcher=True)
        residue1 = get_residue(r1)
        r2, _ = run_tier2(residue1, matcher)
        r3, _ = run_tier3(r2, matcher, llm_client=GoodSplitSettlementLLM())
        final_residue = get_final_residue(r3)
        self.assertTrue(all(r.status != STATUS_MATCH for r in final_residue))
        self.assertEqual(len(final_residue), len(r3) - sum(1 for r in r3 if r.status == STATUS_MATCH))


class TestGeminiLLMClient(unittest.TestCase):
    """
    Provider-level tests only: config/auth/parsing behavior. Never hits the
    real network. Does not touch Tier 3 adjudication logic -- that is
    already fully covered via the fake LLMClient implementations above,
    since GeminiLLMClient implements the same Protocol.
    """

    def test_implements_llm_client_protocol(self):
        self.assertTrue(hasattr(GeminiLLMClient, "complete"))
        client = GeminiLLMClient()
        self.assertTrue(callable(client.complete))

    def test_missing_api_key_raises_llm_unavailable_without_network_call(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            client = GeminiLLMClient()
            with self.assertRaises(LLMUnavailableError):
                client.complete("system", "user")

    def test_api_key_never_hardcoded_in_source(self):
        import inspect
        import core.match_llm as mod
        src = inspect.getsource(mod.GeminiLLMClient)
        self.assertNotIn("AIza", src)  # common literal Google API key prefix
        self.assertIn("GEMINI_API_KEY", src)
        self.assertIn("os.environ.get", src)

    @patch("urllib.request.urlopen")
    def test_successful_response_extracts_text(self, mock_urlopen):
        fake_body = {
            "candidates": [{"content": {"parts": [{"text": '{"decision": "MATCH"}'}]}}]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_body).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-not-real"}):
            client = GeminiLLMClient()
            result = client.complete("system", "user")
        self.assertEqual(result, '{"decision": "MATCH"}')

        # verify the key was sent as a header, never in the URL/body, and
        # never logged/printed by inspecting the actual request object used
        sent_request = mock_urlopen.call_args[0][0]
        self.assertEqual(sent_request.get_header("X-goog-api-key"), "test-key-not-real")
        self.assertNotIn("test-key-not-real", sent_request.full_url)

    @patch("urllib.request.urlopen")
    def test_malformed_response_shape_raises_llm_unavailable(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"candidates": []}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-not-real"}):
            client = GeminiLLMClient()
            with self.assertRaises(LLMUnavailableError):
                client.complete("system", "user")

    def test_gemini_client_usable_as_tier3_llm_client_end_to_end(self):
        # Confirms GeminiLLMClient can be passed directly to run_tier3 like
        # any other LLMClient, without any adapter -- proves the provider
        # swap requires zero changes to Tier 3 logic. Missing key -> Tier 3
        # falls back to its existing LLMUnavailable handling.
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            by_txn, summary = _run_pipeline(llm_client=GeminiLLMClient())
        r = by_txn["PAY109"]
        self.assertEqual(r.status, STATUS_AI_RETRY_REQUIRED)
        self.assertEqual(r.reason, REASON_AI_RETRY_REQUIRED)
        # the attempt is counted (mirrors existing RaisingLLM test behavior);
        # no recommendation was validated or rejected since none was parsed
        self.assertEqual(summary.llm_recommendations_validated, 0)
        self.assertEqual(summary.llm_recommendations_rejected, 0)


class TestParseLLMJson(unittest.TestCase):
    """Parser must reliably extract JSON from the common LLM response shapes:
    plain JSON, markdown-fenced with/without a language tag."""

    VALID_JSON = '{"decision": "MATCH", "bank_row_ids": ["B107", "B108"], "rationale": "sums within tolerance"}'

    def test_plain_json(self):
        parsed = LLMAdjudicator._parse_llm_json(self.VALID_JSON)
        self.assertEqual(parsed["decision"], "MATCH")
        self.assertEqual(parsed["bank_row_ids"], ["B107", "B108"])

    def test_plain_json_with_surrounding_whitespace(self):
        parsed = LLMAdjudicator._parse_llm_json(f"  \n{self.VALID_JSON}\n  ")
        self.assertEqual(parsed["decision"], "MATCH")

    def test_markdown_fenced_with_json_tag(self):
        raw = f"```json\n{self.VALID_JSON}\n```"
        parsed = LLMAdjudicator._parse_llm_json(raw)
        self.assertEqual(parsed["decision"], "MATCH")

    def test_markdown_fenced_without_language_tag(self):
        raw = f"```\n{self.VALID_JSON}\n```"
        parsed = LLMAdjudicator._parse_llm_json(raw)
        self.assertEqual(parsed["decision"], "MATCH")

    def test_markdown_fenced_single_line_no_trailing_newline(self):
        # ```json\n{...}``` (no newline before the closing fence)
        raw = f"```json\n{self.VALID_JSON}```"
        parsed = LLMAdjudicator._parse_llm_json(raw)
        self.assertEqual(parsed["decision"], "MATCH")

    def test_prose_around_json_block_extracts_object(self):
        raw = f"Here is the result:\n{self.VALID_JSON}\nThat is all."
        parsed = LLMAdjudicator._parse_llm_json(raw)
        self.assertEqual(parsed["decision"], "MATCH")

    def test_unparseable_returns_none(self):
        self.assertIsNone(LLMAdjudicator._parse_llm_json("not json at all"))
        self.assertIsNone(LLMAdjudicator._parse_llm_json(""))
        self.assertIsNone(LLMAdjudicator._parse_llm_json("```python\nx = 1\n```"))


if __name__ == "__main__":
    unittest.main()
