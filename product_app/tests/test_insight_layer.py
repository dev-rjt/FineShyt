import os
import unittest
from unittest.mock import Mock, patch

import insight_layer
from insight_layer import explain, llm_facts, ollama_configured


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
ESTIMATE_PAYLOAD = {
    **PAYLOAD,
    "impact_status": "OK",
    "estimate_low": 2414.7,
    "estimate_central": 2536.22,
    "estimate_high": 2657.75,
    "avoided_kg_co2e_per_year": 2536.22,
    "horizon": "12 months",
}
GOOD_ESTIMATE = ("EV Finance may suit you because you drive a lot each year. Switching could potentially avoid between "
                 "2,414.7 and 2,657.75 kg CO2e per year, though this is an estimate, not a measured result.")


def reply(content):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"done": True, "done_reason": "stop", "message": {"content": content}}
    return response


class InsightLayerTests(unittest.TestCase):
    CLOUD_ENV = {
        "OLLAMA_API_KEY": "private-key",
        "OLLAMA_BASE_URL": "https://ollama.com",
        "OLLAMA_MODEL": "gemma4:31b",
        "OLLAMA_ALLOW_LAN": "false",
    }

    def setUp(self):
        insight_layer._EXPLANATION_CACHE.clear()

    def explain_with(self, payload, content, **kwargs):
        with patch.dict(os.environ, self.CLOUD_ENV, clear=True), patch(
            "insight_layer.requests.post", return_value=reply(content)
        ) as post:
            return (*explain(payload, **kwargs), post)

    def test_llm_sees_only_preformatted_facts(self):
        facts = llm_facts(ESTIMATE_PAYLOAD)
        self.assertEqual(facts["co2e_low"], "2,414.7")
        self.assertEqual(facts["co2e_high"], "2,657.75")
        for hidden in ("propensity_pct", "confidence_pct", "product_id", "reason_codes", "data_as_of", "action"):
            self.assertNotIn(hidden, facts)

    def test_valid_estimate_gets_compliance_sentence_from_code(self):
        text, source, _ = self.explain_with(ESTIMATE_PAYLOAD, GOOD_ESTIMATE)
        self.assertEqual(source, "llm")
        self.assertTrue(text.startswith(GOOD_ESTIMATE))
        self.assertIn("subject to eligibility checks", text)
        self.assertIn("not an offer or approval", text)
        self.assertTrue(text.endswith("Based on data as of 2025-12-31."))

    def test_rejected_llm_text_falls_back_to_template(self):
        cases = {
            "missing estimate range": "EV Finance may suit you. You could avoid an estimated 2,657.75 kg CO2e per year.",
            "forbidden wording": GOOD_ESTIMATE + " You are eligible for this product.",
            "ungrounded number": GOOD_ESTIMATE + " That is about 3,000 kg over two years.",
            "percentage": GOOD_ESTIMATE + " There is a 72% chance you will like it.",
            "product not named": "This may suit you. Switching could potentially avoid between 2,414.7 and 2,657.75 kg CO2e, an estimate.",
        }
        for reason, content in cases.items():
            with self.subTest(reason=reason):
                insight_layer._EXPLANATION_CACHE.clear()
                text, source, _ = self.explain_with(ESTIMATE_PAYLOAD, content)
                self.assertEqual(source, f"template (llm rejected: {reason})")
                self.assertIn("not an offer or approval", text)

    def test_insufficient_data_must_be_stated(self):
        _, source, _ = self.explain_with(PAYLOAD, "EV Finance may suit you because you drive a lot each year.")
        self.assertEqual(source, "template (llm rejected: missing insufficient-data statement)")

    def test_repeat_payload_is_served_from_cache(self):
        with patch.dict(os.environ, self.CLOUD_ENV, clear=True), patch(
            "insight_layer.requests.post", return_value=reply(GOOD_ESTIMATE)
        ) as post:
            first = explain(ESTIMATE_PAYLOAD)
            second = explain(ESTIMATE_PAYLOAD)
        self.assertEqual(first, second)
        self.assertEqual(post.call_count, 1)

    def test_timeout_override_is_capped_by_configuration(self):
        _, _, post = self.explain_with(ESTIMATE_PAYLOAD, GOOD_ESTIMATE, timeout=20)
        self.assertEqual(post.call_args.kwargs["timeout"], 20)

    def test_suppressed_payload_never_reaches_llm(self):
        with patch.dict(os.environ, self.CLOUD_ENV, clear=True), patch("insight_layer.requests.post") as post:
            _, source = explain({**ESTIMATE_PAYLOAD, "recommended": False})
        self.assertEqual(source, "template")
        post.assert_not_called()

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
