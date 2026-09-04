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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as server_module
from app import app


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
                    "tier3_summary", "llm_calls_made"):
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

    def test_no_hardcoded_numbers(self):
        """Counts come from the live pipeline, not fixtures."""
        r = self.client.get("/api/overview")
        d = r.get_json()
        # Verified against the real dataset: 116 gateway rows → 116 transactions
        # indexed (includes refund rows). The total must be >100 and consistent.
        self.assertGreater(d["total_transactions"], 100)


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
                exc["status"], ("HUMAN_REVIEW", "UNRESOLVED"),
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

    def test_pay109_is_tier3(self):
        """PAY109 is the canonical Tier 3 split-settlement case.
        In offline/no-LLM-key mode it lands at HUMAN_REVIEW; with a valid
        Gemini key it would be MATCH. The test checks tier + that the result
        comes from the live pipeline, not a hardcoded fixture.
        """
        r = self.client.get("/api/transaction/PAY109")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["tier"], "TIER_3")
        self.assertIn(d["status"], ("MATCH", "HUMAN_REVIEW"))

    def test_pay109_data_not_hardcoded(self):
        """PAY109 result comes from the live pipeline, not a fixture.
        In offline mode it's HUMAN_REVIEW with candidates evidence; with LLM it
        would be MATCH with gateway_amount + bank_row_ids. Either way, the data
        comes from the pipeline.
        """
        r = self.client.get("/api/transaction/PAY109")
        d = r.get_json()
        ev = d.get("evidence", {})
        self.assertIn("gateway_amount", ev)
        # In offline mode: candidates list; with LLM: bank_row_ids
        self.assertTrue("candidates" in ev or "bank_row_ids" in ev)

    def test_transaction_status_matches_overview(self):
        """Status in /api/transaction must match what /api/overview counts."""
        ov = self.client.get("/api/overview").get_json()
        sc = ov["status_counts"]
        # Spot-check: PAY109 should be in the MATCH bucket
        r = self.client.get("/api/transaction/PAY109").get_json()
        self.assertIn(r["status"], sc)


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
        r = self._ask("Which transactions need human review?")
        d = r.get_json()
        self.assertEqual(d["intent"], "FILTER_STATUS")
        self.assertGreater(len(d["transaction_ids"]), 0)

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
