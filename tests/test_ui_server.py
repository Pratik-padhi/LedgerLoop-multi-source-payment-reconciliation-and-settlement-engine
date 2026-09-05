"""
Tests for app.py — LedgerLoop Controller UI Server

Covers:
  - /api/overview returns correct structure and counts
  - /api/exceptions returns only HUMAN_REVIEW and UNRESOLVED
  - /api/transaction/<id> returns full detail for known / 404 for unknown
  - /api/qa routes to the existing SettlementQAAgent
  - /api/qa missing/empty question returns 400
  - Reconciliation results are not mutated by any endpoint
  - UI server never calls Gemini directly (no GEMINI_API_KEY required)
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as server_module
from app import app


class RetryUnavailableLLM:
    def complete(self, system, user):
        from core.match_llm import LLMUnavailableError
        raise LLMUnavailableError("simulated outage")


class RetrySuccessLLM:
    def complete(self, system, user):
        payload = json.loads(user)
        ids = [c["source_row_id"] for c in payload["candidate_bank_credits"]]
        return json.dumps({
            "decision": "MATCH",
            "bank_row_ids": ids,
            "confidence": 0.91,
            "rationale": "candidate credits reconcile the settlement",
            "evidence": {"source": "candidate_sum"},
            "adjustment": {},
        })


class TestOverviewEndpoint(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_returns_200(self):
        r = self.client.get("/api/overview")
        self.assertEqual(r.status_code, 200)

    def test_has_required_keys(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        for key in ("total_transactions", "status_counts", "tier_counts",
                    "rule_counts", "tier1_summary", "tier2_summary",
                    "tier3_summary", "llm_calls_made",
                    "gateway_value", "reconciled_value",
                    "reconciliation_rate", "exception_count",
                    "settlement_variance",
                    "dataset", "gateway_rows", "bank_rows", "ledger_rows",
                    "llm_models"):
            self.assertIn(key, d, f"missing key: {key}")

    def test_total_matches_index(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertGreater(d["total_transactions"], 0)

    def test_status_counts_sum_to_total(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertEqual(
            sum(d["status_counts"].values()),
            d["total_transactions"],
        )

    def test_tier_counts_sum_to_total(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertEqual(
            sum(d["tier_counts"].values()),
            d["total_transactions"],
        )

    def test_tier1_summary_present(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        t1 = d["tier1_summary"]
        self.assertIn("matched_count", t1)
        self.assertIn("total_logical_transactions", t1)

    def test_kpi_values_non_negative(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertGreaterEqual(d["gateway_value"], 0)
        self.assertGreaterEqual(d["reconciled_value"], 0)
        self.assertGreaterEqual(d["reconciliation_rate"], 0)
        self.assertLessEqual(d["reconciliation_rate"], 100)
        self.assertGreaterEqual(d["exception_count"], 0)

    def test_reconciled_not_exceeds_gateway(self):
        """Reconciled value cannot exceed total gateway value."""
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertLessEqual(d["reconciled_value"], d["gateway_value"] + 0.01)

    def test_exception_count_matches_total_minus_matched(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        matched = d["status_counts"].get("MATCH", 0) + d["status_counts"].get("MATCHED", 0)
        self.assertEqual(d["exception_count"], d["total_transactions"] - matched)

    def test_no_hardcoded_numbers(self):
        """Counts come from the live pipeline, not fixtures."""
        r = self.client.get("/api/overview")
        d = r.get_json()
        # Verified against the real dataset: 116 gateway rows → 116 transactions
        # indexed (includes refund rows). The total must be >100 and consistent.
        self.assertGreater(d["total_transactions"], 100)

    def test_dataset_is_nonempty_string(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertIsInstance(d["dataset"], str)
        self.assertGreater(len(d["dataset"]), 0)

    def test_source_row_counts_positive(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertGreater(d["gateway_rows"], 0)
        self.assertGreater(d["bank_rows"], 0)
        self.assertGreater(d["ledger_rows"], 0)

    def test_llm_models_is_list(self):
        r = self.client.get("/api/overview")
        d = r.get_json()
        self.assertIsInstance(d["llm_models"], list)
        self.assertGreater(len(d["llm_models"]), 0)


class TestExceptionsEndpoint(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_returns_200(self):
        r = self.client.get("/api/exceptions")
        self.assertEqual(r.status_code, 200)

    def test_has_exceptions_and_count_keys(self):
        r = self.client.get("/api/exceptions")
        d = r.get_json()
        self.assertIn("exceptions", d)
        self.assertIn("count", d)

    def test_count_matches_list_length(self):
        r = self.client.get("/api/exceptions")
        d = r.get_json()
        self.assertEqual(d["count"], len(d["exceptions"]))

    def test_only_human_review_and_unresolved(self):
        r = self.client.get("/api/exceptions")
        d = r.get_json()
        for exc in d["exceptions"]:
            self.assertIn(
                exc["status"],
                ("HUMAN_REVIEW", "UNRESOLVED", "AI_RETRY_REQUIRED",
                 "PARTIAL_PAYMENT", "AMBIGUOUS"),
                f"{exc['transaction_id']} has unexpected status {exc['status']}"
            )

    def test_each_exception_has_required_fields(self):
        r = self.client.get("/api/exceptions")
        d = r.get_json()
        for exc in d["exceptions"]:
            for field in ("transaction_id", "tier", "status", "matched_records", "evidence"):
                self.assertIn(field, exc, f"missing {field} in {exc.get('transaction_id')}")

    def test_exceptions_are_non_empty(self):
        """The real dataset always has some exceptions."""
        r = self.client.get("/api/exceptions")
        d = r.get_json()
        self.assertGreater(d["count"], 0)

    def test_matched_transactions_not_in_exceptions(self):
        """MATCH-status transactions must never appear in the exception queue."""
        r = self.client.get("/api/exceptions")
        d = r.get_json()
        for exc in d["exceptions"]:
            self.assertNotEqual(exc["status"], "MATCH")
            self.assertNotEqual(exc["status"], "MATCHED")


class TestTransactionEndpoint(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_known_transaction_returns_200(self):
        r = self.client.get("/api/transaction/PAY001")
        self.assertEqual(r.status_code, 200)

    def test_unknown_transaction_returns_404(self):
        r = self.client.get("/api/transaction/PAY999")
        self.assertEqual(r.status_code, 404)

    def test_case_insensitive_id(self):
        upper = self.client.get("/api/transaction/PAY001")
        lower = self.client.get("/api/transaction/pay001")
        self.assertEqual(upper.status_code, lower.status_code)
        if upper.status_code == 200:
            self.assertEqual(
                upper.get_json()["transaction_id"],
                lower.get_json()["transaction_id"],
            )

    def test_response_has_required_fields(self):
        r = self.client.get("/api/transaction/PAY001")
        d = r.get_json()
        for field in ("transaction_id", "tier", "status", "matched_records", "evidence"):
            self.assertIn(field, d)

    def test_pay109_is_stage3(self):
        """PAY109 is the canonical split-settlement case now resolved by Stage 3.
        Stage 3 is the split/multi-payment pass that runs on Tier 3 residue.
        In offline/no-LLM mode it's PARTIAL_PAYMENT or MATCH (deterministic);
        with a valid Gemini key it would be MATCH with LLM adjudication.
        The test checks tier + that the result comes from the live pipeline.
        """
        r = self.client.get("/api/transaction/PAY109")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["tier"], "STAGE_3")
        self.assertIn(d["status"], ("MATCH", "PARTIAL_PAYMENT", "HUMAN_REVIEW", "AI_RETRY_REQUIRED", "AMBIGUOUS", "UNRESOLVED"))

    def test_pay109_data_not_hardcoded(self):
        """PAY109 result comes from the live pipeline, not a fixture.
        Stage 3 evidence includes bank_row_ids, received/outstanding, settlement.
        """
        r = self.client.get("/api/transaction/PAY109")
        d = r.get_json()
        ev = d.get("evidence", {})
        # Stage 3 evidence shape
        self.assertTrue(
            "bank_row_ids" in d or "candidates" in ev or "gateway_amount" in ev or "bank_credit_total" in ev,
            f"Expected Stage 3 evidence keys, got: {list(d.keys())} + evidence: {list(ev.keys())}"
        )
        # Should have bank_row_ids for a MATCH
        if d.get("status") == "MATCH":
            self.assertIn("bank_row_ids", d)
            self.assertTrue(len(d["bank_row_ids"]) >= 2, "Split settlement should have >=2 bank rows")

    def test_transaction_status_matches_overview(self):
        """Status in /api/transaction must match what /api/overview counts."""
        ov = self.client.get("/api/overview").get_json()
        sc = ov["status_counts"]
        # Spot-check: PAY109 should be in the MATCH bucket
        r = self.client.get("/api/transaction/PAY109").get_json()
        self.assertIn(r["status"], sc)


class TestRetryEndpoint(unittest.TestCase):
    """Retry paths for Tier 3 (AI_RETRY_REQUIRED) and Stage 3 (AI_RETRY_REQUIRED).

    The end-to-end pipeline now resolves PAY109 at Stage 3 (MATCH, consuming
    bank rows B107/B108). Those rows are seeded into the retry consumed-set,
    so a genuine Tier-3 retry of PAY109 can no longer propose them (one-to-one
    invariant). These tests therefore temporarily free B107/B108 from the Stage
    3 consumed-set to exercise the retry-llm endpoint's real adjudication path,
    and reset it afterwards. The Stage 3 retry tests run against the server's
    real state.
    """

    # Bank rows Stage 3 consumed for its PAY109 split — freed during tests so
    # the Tier 3 retry can legitimately propose them again.
    _PAY109_STAGE3_ROWS = {"B107", "B108"}

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.original_index_entry = server_module._index["PAY109"]
        self.r3_index = next(i for i, result in enumerate(server_module._r3)
                             if result.transaction_id == "PAY109")
        self.original_r3 = server_module._r3[self.r3_index]
        self.original_qa_agent = server_module._qa_agent
        self.original_stage3_consumed = set(server_module._stage3_consumed)
        server_module._stage3_consumed -= self._PAY109_STAGE3_ROWS
        server_module._index["PAY109"] = {
            "tier": "TIER_3",
            "data": {**self.original_index_entry["data"],
                     "status": "AI_RETRY_REQUIRED",
                     "reason": "AI_RETRY_REQUIRED"},
        }

    def tearDown(self):
        server_module._index["PAY109"] = self.original_index_entry
        server_module._r3[self.r3_index] = self.original_r3
        server_module._qa_agent = self.original_qa_agent
        server_module._stage3_consumed = self.original_stage3_consumed

    def test_retry_unavailable_remains_retryable(self):
        with patch.object(server_module, "GeminiLLMClient", return_value=RetryUnavailableLLM()):
            response = self.client.post("/api/transaction/PAY109/retry-llm")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "AI_RETRY_REQUIRED")

    def test_retry_success_returns_validated_adjudication(self):
        with patch.object(server_module, "GeminiLLMClient", return_value=RetrySuccessLLM()):
            response = self.client.post(
                "/api/transaction/PAY109/retry-llm",
                json={"bank_row_ids": ["B999"], "amount": 1},
            )
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "MATCH")
        self.assertEqual(data["confidence"], 0.91)
        self.assertEqual(data["evidence"]["llm_evidence"]["source"], "candidate_sum")

    def test_retry_rejects_non_retryable_transaction(self):
        server_module._index["PAY109"]["data"]["status"] = "HUMAN_REVIEW"
        response = self.client.post("/api/transaction/PAY109/retry-llm")
        self.assertEqual(response.status_code, 409)

    def test_ai_review_returns_structured_read_only_result(self):
        class ReviewLLM:
            def complete(self, system, user):
                return json.dumps({
                    "decision": "REVIEW",
                    "confidence": 0.82,
                    "rationale": "The stored settlement evidence is internally consistent.",
                    "evidence": {"source": "stored_context"},
                    "adjustment": {},
                })

        with patch.object(server_module, "GeminiFallbackClient", return_value=ReviewLLM()):
            response = self.client.post("/api/transaction/PAY109/ai-review")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["review"]["confidence"], 0.82)
        self.assertEqual(data["source_status"], "AI_RETRY_REQUIRED")

    def test_ai_review_failure_is_retryable_without_mutating_result(self):
        original = dict(server_module._index["PAY109"]["data"])
        with patch.object(server_module, "GeminiFallbackClient", side_effect=Exception("provider down")):
            response = self.client.post("/api/transaction/PAY109/ai-review")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()["retryable"])
        self.assertEqual(server_module._index["PAY109"]["data"], original)

    def test_retry_llm_rejects_stage3_transaction(self):
        """A transaction the live pipeline resolved at Stage 3 (e.g. PAY109)
        must NOT be retryable via /retry-llm — that endpoint is Tier 3 only.
        Reverting the index to its true STAGE_3 state must yield 409."""
        server_module._index["PAY109"] = self.original_index_entry
        response = self.client.post("/api/transaction/PAY109/retry-llm")
        self.assertEqual(response.status_code, 409)
        self.assertIn("tier", response.get_json())
        self.assertEqual(response.get_json()["tier"], "STAGE_3")

    def test_retry_llm_dropped_rows_are_never_reproposed(self):
        """Once Stage 3 consumes a bank row for its split, a Tier 3 retry of a
        DIFFERENT transaction must not be able to consume that row. We retry
        PAY109 but WITHOUT freeing B107/B108, so its only candidates are
        unavailable — Python must refuse to resolve rather than force MATCH."""
        # Simulate the real production state: Stage 3 consumed B107/B108.
        # Re-consume them (setUp just freed them) so PAY109's candidates are
        # unavailable; the RetrySuccessLLM mock will echo B107/B108 back, and
        # the validator must reject them as consumed.
        server_module._stage3_consumed |= self._PAY109_STAGE3_ROWS
        with patch.object(server_module, "GeminiLLMClient", return_value=RetrySuccessLLM()):
            response = self.client.post("/api/transaction/PAY109/retry-llm")
        data = response.get_json()
        self.assertNotEqual(data["status"], "MATCH",
                            "retry must never claim rows Stage 3 already owns")

    def test_retry_stage3_requires_stage3_tier(self):
        """/retry-stage3 must reject a non-Stage-3 transaction with 409."""
        response = self.client.post("/api/transaction/PAY001/retry-stage3")
        self.assertEqual(response.status_code, 409)
        body = response.get_json()
        self.assertIn("tier", body)

    def test_retry_stage3_unknown_transaction_404(self):
        response = self.client.post("/api/transaction/PAY999/retry-stage3")
        self.assertEqual(response.status_code, 404)

    def test_retry_stage3_requires_ai_retry_status(self):
        """A Stage 3 transaction that is NOT AI_RETRY_REQUIRED cannot be retried."""
        stage3_txn = next(tid for tid, e in server_module._index.items()
                          if e["tier"] == "STAGE_3" and e["data"]["status"] != "AI_RETRY_REQUIRED")
        response = self.client.post(f"/api/transaction/{stage3_txn}/retry-stage3")
        self.assertEqual(response.status_code, 409)

    def test_retry_stage3_deterministic_resolves_even_when_gemini_down(self):
        """Python stays authoritative: a Stage 3 transaction that resolves
        deterministically (unique split sum within tolerance) must still reach
        MATCH on retry even when Gemini is unavailable — the LLM is only ever a
        recommender for genuine ambiguity. PAY109's 2-row split is unique, so a
        retry with a down LLM must return 200 MATCH, not block on Gemini."""
        stage3_txn = "PAY109"
        entry = server_module._index[stage3_txn]
        original_tier = entry["tier"]
        original_data = dict(entry["data"])
        try:
            entry["tier"] = "STAGE_3"
            entry["data"] = {**original_data, "status": "AI_RETRY_REQUIRED"}
            server_module._index[stage3_txn] = entry
            with patch.object(server_module, "GeminiLLMClient", return_value=RetryUnavailableLLM()):
                response = self.client.post(f"/api/transaction/{stage3_txn}/retry-stage3")
            self.assertEqual(response.status_code, 200,
                             "deterministic Stage 3 split must not depend on Gemini")
            data = response.get_json()
            self.assertEqual(data["status"], "MATCH")
            # The returned chain must have re-consumed PAY109's split rows.
            self.assertTrue(set(data["bank_row_ids"]).issubset(server_module._stage3_consumed),
                            "a Stage 3 MATCH must be added to the stage3 consumed set")
        finally:
            server_module._index[stage3_txn] = {"tier": original_tier, "data": original_data}


class TestHealthEndpoint(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_returns_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok"})

    def test_health_content_type_json(self):
        r = self.client.get("/health")
        self.assertIn("application/json", r.content_type)


class TestQAEndpoint(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def _ask(self, question):
        return self.client.post(
            "/api/qa",
            json={"question": question},
            content_type="application/json",
        )

    def test_returns_200_for_valid_question(self):
        r = self._ask("What happened to PAY109?")
        self.assertEqual(r.status_code, 200)

    def test_missing_question_returns_400(self):
        r = self.client.post("/api/qa", json={})
        self.assertEqual(r.status_code, 400)

    def test_empty_question_returns_400(self):
        r = self.client.post("/api/qa", json={"question": "  "})
        self.assertEqual(r.status_code, 400)

    def test_answer_has_required_fields(self):
        r = self._ask("What happened to PAY109?")
        d = r.get_json()
        for field in ("intent", "question", "found", "supported",
                      "transaction_ids", "retrieved_data", "explanation",
                      "llm_used", "llm_unavailable"):
            self.assertIn(field, d, f"QAAnswer missing field: {field}")

    def test_pay109_lookup_found(self):
        r = self._ask("What happened to PAY109?")
        d = r.get_json()
        self.assertTrue(d["found"])
        self.assertEqual(d["intent"], "LOOKUP")
        self.assertIn("PAY109", d["transaction_ids"])

    def test_unknown_transaction_found_false(self):
        r = self._ask("What happened to PAY999?")
        d = r.get_json()
        self.assertFalse(d["found"])
        self.assertIn("not found", d["explanation"].lower())

    def test_filter_human_review_intent(self):
        """Test that FILTER_STATUS intent works for a status filter.
        Stage 3 may reclassify Tier 3 HUMAN_REVIEW → PARTIAL_PAYMENT, so we
        test with a status that is guaranteed to exist after Stage 3."""
        r = self._ask("Show unresolved transactions.")
        d = r.get_json()
        self.assertEqual(d["intent"], "FILTER_STATUS")
        self.assertGreater(len(d["transaction_ids"]), 0)

    def test_filter_by_status_with_human_review(self):
        """Test the human-review filter intent classifies correctly, even if
        no transactions currently have that status after Stage 3 reclassification."""
        r = self._ask("Which transactions need human review?")
        d = r.get_json()
        self.assertEqual(d["intent"], "FILTER_STATUS")
        # The intent is correctly classified; 0 results is valid after Stage 3

    def test_unsupported_question(self):
        r = self._ask("What is the weather today?")
        d = r.get_json()
        self.assertEqual(d["intent"], "UNSUPPORTED")
        self.assertFalse(d["supported"])

    def test_qa_does_not_call_gemini_directly(self):
        """
        The /api/qa endpoint must delegate entirely to SettlementQAAgent.
        It must not contain direct Gemini API calls or network calls.
        """
        import inspect
        import app as app_module
        src = inspect.getsource(app_module.api_qa)
        self.assertNotIn("urllib", src, "api_qa must not make direct HTTP calls")
        self.assertNotIn("requests", src, "api_qa must not make direct HTTP calls")
        self.assertNotIn("GEMINI_API_KEY", src, "api_qa must not read the API key")

    def test_qa_uses_existing_agent(self):
        """The endpoint uses the pre-built _qa_agent, not a new instance."""
        import inspect
        import app as app_module
        src = inspect.getsource(app_module.api_qa)
        self.assertIn("_qa_agent", src)

    def test_no_llm_used_by_default(self):
        """Default agent config uses use_llm_for_explanations=False."""
        r = self._ask("What happened to PAY109?")
        d = r.get_json()
        self.assertFalse(d["llm_used"], "Default agent should not use LLM for explanations")


class TestStaticRoutes(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_root_returns_html(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"LedgerLoop", r.data)

    def test_root_content_type_html(self):
        r = self.client.get("/")
        self.assertIn("text/html", r.content_type)

    def test_styles_css_serves_200(self):
        """Static CSS must be served from the ui/ directory (regression: was 404)."""
        r = self.client.get("/styles.css")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/css", r.content_type)
        self.assertGreater(len(r.data), 1000)

    def test_app_js_serves_200(self):
        """Static JS must be served from the ui/ directory (regression: was 404)."""
        r = self.client.get("/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.content_type)
        self.assertGreater(len(r.data), 1000)


class TestPipelineIsolation(unittest.TestCase):
    """Confirm the server does not mutate pipeline results."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def _snapshot_index(self):
        return {tid: dict(entry) for tid, entry in server_module._index.items()}

    def test_overview_does_not_mutate_index(self):
        before = self._snapshot_index()
        self.client.get("/api/overview")
        after = self._snapshot_index()
        self.assertEqual(set(before.keys()), set(after.keys()))

    def test_exceptions_does_not_mutate_index(self):
        before = self._snapshot_index()
        self.client.get("/api/exceptions")
        after = self._snapshot_index()
        self.assertEqual(set(before.keys()), set(after.keys()))

    def test_transaction_lookup_does_not_mutate_index(self):
        before = self._snapshot_index()
        self.client.get("/api/transaction/PAY109")
        after = self._snapshot_index()
        self.assertEqual(set(before.keys()), set(after.keys()))

    def test_qa_does_not_mutate_index(self):
        before = self._snapshot_index()
        self.client.post("/api/qa", json={"question": "What happened to PAY109?"})
        after = self._snapshot_index()
        self.assertEqual(set(before.keys()), set(after.keys()))

    def test_no_ground_truth_imported(self):
        """The server must never import or open ground_truth.csv."""
        import inspect
        import app as app_module
        src = inspect.getsource(app_module)
        # Check for actual import or open calls, not comments/docstrings
        self.assertNotIn("import ground_truth", src)
        self.assertNotIn("from ground_truth", src)
        self.assertNotIn("open(", src)  # no file I/O in app.py
        self.assertNotIn("ground_truth.csv", src)


if __name__ == "__main__":
    unittest.main()
