import json
from pathlib import Path
import unittest

import pandas as pd
from jsonschema import Draft202012Validator

from contract_adapter import contract_impact as estimate_impact, contract_reasons, engine_assumption_drift
from insight_layer import REASON_TEXT

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "opportunity_v1.schema.json").read_text())
IMPACT_VALIDATOR = Draft202012Validator({**SCHEMA, **SCHEMA["$defs"]["impact"]})
CONTRACT_KEYS = ["status", "is_estimate", "horizon_months", "method", "metrics", "assumptions", "factors", "missing_inputs"]
ROW = pd.Series({
    "annual_mileage": 9000, "fuel_type_code": 1, "gas_kwh_yr": 10000, "elec_kwh_yr": 3500,
    "paper_share": 0.75, "paper_stmts_yr": 12,
})


class CarbonEngineTests(unittest.TestCase):
    def assert_contract_valid(self, impact):
        errors = list(IMPACT_VALIDATOR.iter_errors({key: impact[key] for key in CONTRACT_KEYS}))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_every_product_returns_ordered_range_and_provenance(self):
        for product in ["EV_FINANCE", "GREEN_HOME", "SOLAR_FINANCE"]:
            impact = estimate_impact(product, ROW)
            self.assertEqual(impact["status"], "OK")
            self.assert_contract_valid(impact)
            co2e = next(metric for metric in impact["metrics"] if metric["metric"] == "CO2E_KG")
            self.assertLess(co2e["low"], co2e["central"])
            self.assertLess(co2e["central"], co2e["high"])
            self.assertEqual(impact["estimate_central"], co2e["central"])
            self.assertTrue(impact["assumptions"])
            self.assertTrue(impact["factors"])
            for factor in impact["factors"]:
                self.assertTrue(factor["factor_id"])
                self.assertIsNotNone(factor["source_year"])

    def test_paperless_reports_paper_and_digital_without_unsourced_carbon(self):
        impact = estimate_impact("PAPERLESS", ROW)
        self.assertEqual(impact["status"], "OK")
        self.assert_contract_valid(impact)
        self.assertEqual([metric["metric"] for metric in impact["metrics"]], ["PAPER_SHEETS", "DIGITAL_ADOPTION_PP"])
        self.assertIsNone(impact["avoided_kg_co2e_per_year"])
        self.assertNotIn("estimate_low", impact)
        self.assertEqual(impact["factors"], [])
        self.assertEqual(impact["paper_statements_avoided"], 12)

    def test_solar_scenario_cannot_displace_more_than_annual_use(self):
        impact = estimate_impact("SOLAR_FINANCE", pd.Series({"elec_kwh_yr": 50}))
        displaced = next(metric for metric in impact["metrics"] if metric["metric"] == "ENERGY_KWH")
        self.assertLessEqual(displaced["high"], 50)
        self.assertGreaterEqual(impact["scenario_kg_co2e"], 0)

    def test_missing_inputs_are_not_imputed(self):
        impact = estimate_impact("EV_FINANCE", pd.Series({"annual_mileage": None, "fuel_type_code": 1}))
        self.assertEqual(impact["status"], "INSUFFICIENT_DATA")
        self.assertEqual(impact["metrics"], [])
        self.assertIn("annual_mileage", impact["missing_inputs"])
        self.assert_contract_valid(impact)

    def test_engine_specific_statuses_map_to_insufficient_data(self):
        impact = estimate_impact("PAPERLESS", pd.Series({"paper_share": 1.5, "paper_stmts_yr": 12}))
        self.assertEqual(impact["engine_status"], "INVALID_DATA")
        self.assertEqual(impact["status"], "INSUFFICIENT_DATA")
        self.assert_contract_valid(impact)

    def test_assumption_table_matches_engine_constants(self):
        self.assertEqual(engine_assumption_drift(), {})


class FakeModel:
    feats = ["branch_visits_m", "urban", "income_idx", "annual_mileage"]
    reference = pd.Series({"branch_visits_m": 2.0, "urban": 1.0, "income_idx": 2.0, "annual_mileage": 8000.0})

    def __init__(self, evidence):
        self._evidence = evidence

    def evidence(self, X, top_k=3):
        return [self._evidence]


class ReasonCodeTests(unittest.TestCase):
    def test_codes_follow_observed_direction_and_vocabulary(self):
        model = FakeModel([
            {"feature": "urban", "observed_value": 0.0},  # rural raised the score: "urban charging" would mislead
            {"feature": "branch_visits_m", "observed_value": 0.5},  # below median: LOW_BRANCH_USE is truthful
            {"feature": "income_idx", "observed_value": 4.0},  # affordability wording intentionally unmapped
            {"feature": "annual_mileage", "observed_value": 15000.0},
        ])
        codes = contract_reasons(model, pd.DataFrame([{}]))[0]
        self.assertEqual(codes, ["LOW_BRANCH_USE", "HIGH_ANNUAL_MILEAGE"])
        self.assertTrue(set(codes) <= set(REASON_TEXT))


if __name__ == "__main__":
    unittest.main()
