import os
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker

from auth import hash_password
from api import LoginRequest, get_customer, get_customer_audit, get_feature_weights, get_opportunities, health, login, require_bank
from api_service import API_LLM_TIMEOUT_SECONDS, score_snapshot


SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "opportunity_v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


class ApiIntegrationTests(unittest.TestCase):
    BANK_PASSWORD = "bank-test-password"
    CUSTOMER_PASSWORD = "customer-test-password"
    TEST_ENV = {
        "BANK_DEMO_ID": "bank_manager",
        "BANK_DEMO_PASSWORD_HASH": hash_password(BANK_PASSWORD),
        "CUSTOMER_DEMO_ID": "C12558",
        "CUSTOMER_DEMO_PASSWORD_HASH": hash_password(CUSTOMER_PASSWORD),
        "APP_SESSION_SECRET": "test-session-secret-with-more-than-24-chars",
    }

    def setUp(self):
        environment = patch.dict(os.environ, self.TEST_ENV, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def login(self, username, password):
        return login(LoginRequest(username=username, password=password))["principal"]

    def test_health_describes_complete_stack(self):
        body = health()
        self.assertEqual(body["customers"], 5000)
        self.assertEqual(body["opportunity_records"], 20000)
        self.assertEqual(body["components"]["backend"], "fastapi")
        self.assertEqual(body["components"]["impact"], "deterministic_carbon_engine")

    def test_customer_is_scoped_to_own_live_score(self):
        principal = self.login(os.environ["CUSTOMER_DEMO_ID"], self.CUSTOMER_PASSWORD)
        customer_id = os.environ["CUSTOMER_DEMO_ID"]
        own = get_opportunities(customer_id, principal)
        self.assertLessEqual(len(own["items"]), 4)
        self.assertTrue(own["items"])
        self.assertTrue(all(item["status"] != "SUPPRESSED" for item in own["items"]))
        self.assertEqual(own["scoring_source"], "live_model")
        with self.assertRaises(HTTPException) as caught:
            get_opportunities("C10001", principal)
        self.assertEqual(caught.exception.status_code, 403)

    def test_bank_can_access_portfolio_and_customer(self):
        principal = self.login(os.environ["BANK_DEMO_ID"], self.BANK_PASSWORD)
        weights = get_feature_weights("EV_FINANCE", principal)
        self.assertGreater(len(weights["items"]), 5)
        customer = get_opportunities("C12558", principal)
        self.assertTrue(all(item["status"] != "SUPPRESSED" for item in customer["items"]))
        profile = get_customer("C12558", principal)
        self.assertEqual(profile["customer_id"], "C12558")
        self.assertIn("data_quality", profile)

    def test_bank_audit_is_complete_and_contract_valid(self):
        principal = self.login(os.environ["BANK_DEMO_ID"], self.BANK_PASSWORD)
        audit = get_customer_audit("C12558", principal)
        self.assertEqual(len(audit["items"]), 4)
        self.assertEqual(
            {item["opportunity"] for item in audit["items"]},
            {"EV_FINANCE", "GREEN_HOME_LOAN", "SOLAR_FINANCE", "PAPERLESS_BANKING"},
        )
        for item in audit["items"]:
            errors = sorted(VALIDATOR.iter_errors(item), key=lambda error: list(error.path))
            self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_recommended_items_use_verified_llm_wording_with_bounded_timeout(self):
        principal = self.login(os.environ["BANK_DEMO_ID"], self.BANK_PASSWORD)
        with patch("api_service.explain", return_value=("EV Finance may suit you.", "llm")) as explain:
            body = get_opportunities("C12558", principal)
        recommended = [item for item in body["items"] if item["status"] == "RECOMMENDED"]
        self.assertTrue(recommended)
        self.assertEqual(explain.call_count, len(recommended))
        for call in explain.call_args_list:
            self.assertTrue(call.args[0]["recommended"])
            self.assertEqual(call.kwargs["timeout"], API_LLM_TIMEOUT_SECONDS)
        for item in recommended:
            self.assertEqual(item["insight"], {"text": "EV Finance may suit you.", "source": "LLM", "verified": True})
            self.assertEqual(list(VALIDATOR.iter_errors(item)), [])

    def test_co2e_impacts_carry_footprints_matching_the_central_estimate(self):
        principal = self.login(os.environ["BANK_DEMO_ID"], self.BANK_PASSWORD)
        items = get_customer_audit("C12558", principal)["items"]
        checked = 0
        for item in items:
            co2e = next((m for m in item["impact"]["metrics"] if m["metric"] == "CO2E_KG"), None)
            if item["impact"]["status"] == "OK" and co2e:
                baseline, scenario = item["impact"]["baseline_kg_co2e"], item["impact"]["scenario_kg_co2e"]
                self.assertAlmostEqual(baseline - scenario, co2e["central"], delta=0.02)
                checked += 1
            else:
                self.assertNotIn("baseline_kg_co2e", item["impact"])
            self.assertEqual(list(VALIDATOR.iter_errors(item)), [])
        self.assertGreater(checked, 0)

    def test_llm_fallback_is_reported_as_template(self):
        principal = self.login(os.environ["BANK_DEMO_ID"], self.BANK_PASSWORD)
        with patch("api_service.explain", return_value=("Standard wording.", "template (llm error: Timeout)")):
            body = get_opportunities("C12558", principal)
        self.assertTrue(all(item["insight"]["source"] == "TEMPLATE" for item in body["items"] if item["insight"]))

    def test_customer_cannot_open_bank_audit(self):
        principal = self.login(os.environ["CUSTOMER_DEMO_ID"], self.CUSTOMER_PASSWORD)
        with self.assertRaises(HTTPException) as caught:
            require_bank(principal)
        self.assertEqual(caught.exception.status_code, 403)

    def test_ad_hoc_scenario_is_not_persisted_and_rules_win(self):
        result = score_snapshot({
            "customer_id": "TEST-EV",
            "profile": {"age": 35, "income_band": "MID", "home_owner": False},
            "vehicle": {"fuel_type": "ELECTRIC", "vehicle_age": 2, "annual_mileage": None},
            "holdings": [], "transactions": [], "energy_usage": [], "digital_usage": [],
        })
        self.assertEqual(len(result["items"]), 4)
        ev = next(item for item in result["items"] if item["product_id"] == "GP01")
        self.assertEqual(ev["status"], "SUPPRESSED")
        self.assertEqual(ev["gate"]["failed_rules"][0]["code"], "ALREADY_EV_NO_REPLACEMENT_USE_CASE")
        for item in result["items"]:
            self.assertEqual(list(VALIDATOR.iter_errors(item)), [])


if __name__ == "__main__":
    unittest.main()
