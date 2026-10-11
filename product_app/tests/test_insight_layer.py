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

    def test_paperless_without_carbon_factor_reports_paper_only(self):
        payload = {**PAYLOAD, "product": "Paperless Banking", "product_id": "GP04", "impact_status": "OK",
                   "paper_statements_avoided": 23, "paper_sheets_avoided": 69, "avoided_kg_co2e_per_year": None,
                   "action": "Go paperless"}
        self.assertEqual(llm_facts(payload)["impact_status"], "PAPER_ONLY")
        good = "Paperless Banking may suit you. Switching could avoid about 23 paper statements (and 69 sheets) a year."
        text, source, _ = self.explain_with(payload, good)
        self.assertEqual(source, "llm")
        self.assertIn("subject to eligibility checks", text)
        insight_layer._EXPLANATION_CACHE.clear()
        _, source, _ = self.explain_with(payload, good + " That avoids a little carbon too.")
        self.assertEqual(source, "template (llm rejected: carbon claim without a sourced factor)")

    PROFILE = {
        "customer_id": "C99999", "data_as_of": "2025-12-31",
        "profile": {"region": "Wales", "home_owner": 1, "postcode": "CF10 1AA", "income_band": "50-80k"},
        "features": {"electricity_kwh_12m": 3233.7, "electricity_spend_12m": 920.9, "gas_kwh_12m": 15008.9,
                     "gas_spend_12m": 1139.6, "fuel_spend_12m": 1106.1, "digital_transactions_per_month": 56.1,
                     "branch_visits_per_month": 0.0, "paper_statements_12m": 1.0},
        "vehicle": {"vehicle_type": "SUV", "fuel_type": "diesel", "vehicle_age": 6.3, "annual_mileage": 7600.0},
        "holdings": [{"product": "MORTGAGE"}, {"product": "CURRENT_ACCOUNT"}],
    }

    def test_profile_facts_exclude_identifiers_and_read_naturally(self):
        facts = insight_layer.profile_facts(self.PROFILE)
        flat = " ".join(str(value) for value in facts.values())
        for private in ("CF10", "C99999", "50-80k"):
            self.assertNotIn(private, flat)
        text, source = insight_layer.summarise_profile(self.PROFILE, use_llm=False)
        self.assertEqual(source, "template")
        self.assertIn("You drive a 6-year-old diesel SUV", text)
        self.assertIn("rarely visit a branch", text)
        self.assertIn("1 paper statement in", text)
        self.assertIn("a current account and a mortgage", text)

    def test_profile_summary_rejects_advice_and_invented_numbers(self):
        good = "You own your home in Wales. Your home uses about 3,234 kWh of electricity (about £921) a year."
        with patch.dict(os.environ, self.CLOUD_ENV, clear=True), patch("insight_layer.requests.post", return_value=reply(good)):
            text, source = insight_layer.summarise_profile(self.PROFILE)
        self.assertEqual(source, "llm")
        self.assertTrue(text.endswith("Based on your data up to 2025-12-31."))
        for bad, reason in [(good + " You should consider solar panels.", "advice or forbidden wording"),
                            (good + " That is about £2,000 a year.", "ungrounded number")]:
            insight_layer._EXPLANATION_CACHE.clear()
            with patch.dict(os.environ, self.CLOUD_ENV, clear=True), patch("insight_layer.requests.post", return_value=reply(bad)):
                _, source = insight_layer.summarise_profile(self.PROFILE)
            self.assertEqual(source, f"template (llm rejected: {reason})")

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
