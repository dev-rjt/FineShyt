import os
import unittest
from unittest.mock import Mock, patch

from insight_layer import explain, ollama_configured


PAYLOAD = {
    "product": "EV Finance",
    "product_id": "GP01",
    "recommended": True,
    "propensity_pct": 72,
    "confidence_pct": 81,
    "reason_codes": ["HIGH_ANNUAL_MILEAGE"],
    "reasons_plain": ["you drive a lot each year"],
    "data_as_of": "2025-12-31",
    "impact_status": "INSUFFICIENT_DATA",
    "missing_inputs": ["annual_mileage"],
    "action": "Explore EV options",
}


class InsightLayerTests(unittest.TestCase):
    CLOUD_ENV = {
        "OLLAMA_API_KEY": "private-key",
        "OLLAMA_BASE_URL": "https://ollama.com",
        "OLLAMA_MODEL": "gemma4:31b",
        "OLLAMA_ALLOW_LAN": "false",
    }

    def test_cloud_request_uses_ollama_bearer_auth(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "done": True,
            "done_reason": "stop",
            "message": {
                "content": "EV Finance may suit you. We do not have enough data to estimate the carbon impact yet. "
                           "Based on data as of 2025-12-31. Explore EV options"
            },
        }
        with patch.dict(os.environ, self.CLOUD_ENV, clear=True), patch(
            "insight_layer.requests.post", return_value=response
        ) as post:
            text, source = explain(PAYLOAD)

        self.assertEqual(source, "llm")
        self.assertIn("2025-12-31", text)
        request = post.call_args
        self.assertEqual(request.args[0], "https://ollama.com/api/chat")
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer private-key")
        self.assertNotIn("private-key", str(request.kwargs["json"]))
        self.assertFalse(request.kwargs["allow_redirects"])

    def test_missing_cloud_key_uses_safe_template(self):
        env = {**self.CLOUD_ENV, "OLLAMA_API_KEY": ""}
        with patch.dict(os.environ, env, clear=True), patch("insight_layer.requests.post") as post:
            text, source = explain(PAYLOAD)
        self.assertEqual(source, "template")
        self.assertIn("not an offer or approval", text)
        post.assert_not_called()

    def test_lan_origin_is_rejected_without_explicit_opt_in(self):
        env = {**self.CLOUD_ENV, "OLLAMA_BASE_URL": "http://192.168.1.10:11434"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(ollama_configured())

    def test_provider_failure_falls_back_without_leaking_details(self):
        with patch.dict(os.environ, self.CLOUD_ENV, clear=True), patch(
            "insight_layer.requests.post", side_effect=RuntimeError("secret response")
        ):
            text, source = explain(PAYLOAD)
        self.assertEqual(source, "template (llm error: RuntimeError)")
        self.assertNotIn("secret response", text + source)


if __name__ == "__main__":
    unittest.main()
