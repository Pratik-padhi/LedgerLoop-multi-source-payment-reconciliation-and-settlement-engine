import json
import io
import os
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from core.match_llm import GeminiFallbackClient, GeminiLLMClient, LLMUnavailableError


class TestGeminiLLMClient(unittest.TestCase):

    def test_fallback_client_uses_configured_model_order(self):
        with patch.dict(os.environ, {
            "GEMINI_MODEL": "gemini-primary",
            "GEMINI_MODELS": "gemini-secondary,gemini-tertiary",
        }):
            client = GeminiFallbackClient()
        self.assertEqual(client.models, ["gemini-primary", "gemini-secondary", "gemini-tertiary"])
    def test_implements_llm_client_protocol(self):
        self.assertTrue(callable(GeminiLLMClient().complete))

    def test_missing_api_key_raises_without_network_call(self):
        with patch.dict(os.environ, {}, clear=True):
            client = GeminiLLMClient()
            with self.assertLogs("core.match_llm", level="WARNING") as logs:
                with self.assertRaises(LLMUnavailableError):
                    client.complete("system", "user")
            self.assertIn("category=missing_api_key", logs.output[0])

    @patch("urllib.request.urlopen")
    def test_http_failure_logs_status_without_sensitive_data(self, mock_urlopen):
        secret = "test-api-key"
        system = "system instruction with PAY109"
        user = "user payload with B109"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test", 429, "Too Many Requests", {},
            io.BytesIO(b'{"error":"secret provider details"}'),
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": secret}):
            with self.assertLogs("core.match_llm", level="WARNING") as logs:
                with self.assertRaises(LLMUnavailableError):
                    GeminiLLMClient().complete(system, user)

        diagnostic = "\n".join(logs.output)
        self.assertIn("category=http_error", diagnostic)
        self.assertIn("http_status=429", diagnostic)
        for sensitive_value in (secret, system, user, "secret provider details"):
            self.assertNotIn(sensitive_value, diagnostic)

    @patch("urllib.request.urlopen")
    def test_url_failure_logs_sanitized_category(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("private connection detail")

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            with self.assertLogs("core.match_llm", level="WARNING") as logs:
                with self.assertRaises(LLMUnavailableError):
                    GeminiLLMClient().complete("system PAY109", "user B109")

        diagnostic = "\n".join(logs.output)
        self.assertIn("category=url_error", diagnostic)
        self.assertIn("reason_type=str", diagnostic)
        self.assertNotIn("private connection detail", diagnostic)
        self.assertNotIn("PAY109", diagnostic)
        self.assertNotIn("B109", diagnostic)

    @patch("urllib.request.urlopen")
    def test_invalid_response_logs_category_without_response_body(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"provider_detail": "sensitive"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            with self.assertLogs("core.match_llm", level="WARNING") as logs:
                with self.assertRaises(LLMUnavailableError):
                    GeminiLLMClient().complete("system", "user")

        diagnostic = "\n".join(logs.output)
        self.assertIn("category=invalid_response_shape", diagnostic)
        self.assertNotIn("sensitive", diagnostic)

    @patch("urllib.request.urlopen")
    def test_successful_response_extracts_content(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": '{"decision": "MATCH"}'}]}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = GeminiLLMClient().complete("system", "user")

        self.assertEqual(result, '{"decision": "MATCH"}')
        request = mock_urlopen.call_args[0][0]
        self.assertIn("generativelanguage.googleapis.com", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertNotIn("test-key", request.full_url)
        self.assertNotIn("test-key", request.data.decode("utf-8"))

    def test_default_model_from_gemini_environment(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-test"}):
            self.assertEqual(GeminiLLMClient().model, "gemini-test")

    @patch("urllib.request.urlopen")
    def test_request_payload_includes_response_schema(self, mock_urlopen):
        """The generationConfig must include responseSchema so Gemini's API
        enforces structured JSON output matching the reconciliation contract."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": '{"decision": "MATCH", "bank_row_ids": ["B107", "B108"], "rationale": "sums within tolerance"}'}]}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            GeminiLLMClient().complete("system", "user")

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        gen_config = payload["generationConfig"]

        # responseSchema must be present and enforce the exact contract
        self.assertIn("responseSchema", gen_config)
        schema = gen_config["responseSchema"]
        self.assertEqual(schema["type"], "OBJECT")
        self.assertIn("decision", schema["properties"])
        self.assertIn("bank_row_ids", schema["properties"])
        self.assertIn("rationale", schema["properties"])
        self.assertEqual(
            schema["required"],
            ["decision", "bank_row_ids", "confidence", "rationale", "evidence", "adjustment"],
        )
        self.assertEqual(schema["properties"]["confidence"]["minimum"], 0.0)
        self.assertEqual(schema["properties"]["confidence"]["maximum"], 1.0)
        # decision enum must restrict to the three valid dispositions
        self.assertEqual(
            set(schema["properties"]["decision"]["enum"]),
            {"MATCH", "HUMAN_REVIEW", "UNRESOLVED"},
        )

    @patch("urllib.request.urlopen")
    def test_request_payload_includes_json_response_mimetype(self, mock_urlopen):
        """responseMimeType must be application/json to pair with the schema."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": '{"decision": "MATCH"}'}]}}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            GeminiLLMClient().complete("system", "user")

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            payload["generationConfig"]["responseMimeType"], "application/json"
        )


if __name__ == "__main__":
    unittest.main()
