import json
import os
import unittest
from unittest.mock import MagicMock, patch

from core.match_llm import GeminiLLMClient, LLMUnavailableError


class TestGeminiLLMClient(unittest.TestCase):
    def test_implements_llm_client_protocol(self):
        self.assertTrue(callable(GeminiLLMClient().complete))

    def test_missing_api_key_raises_without_network_call(self):
        with patch.dict(os.environ, {}, clear=True):
            client = GeminiLLMClient()
            with self.assertRaises(LLMUnavailableError):
                client.complete("system", "user")

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
        self.assertEqual(schema["required"], ["decision", "bank_row_ids", "rationale"])
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
