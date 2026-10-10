import unittest

import pandas as pd

from carbon_engine import estimate_impact


class CarbonEngineTests(unittest.TestCase):
    def test_every_product_returns_ordered_range_and_provenance(self):
        row = pd.Series({
            "annual_mileage": 9000,
            "fuel_type_code": 1,
            "gas_kwh_yr": 10000,
            "elec_kwh_yr": 3500,
            "paper_share": 0.75,
            "paper_stmts_yr": 12,
        })
        for product in ["EV_FINANCE", "GREEN_HOME", "SOLAR_FINANCE", "PAPERLESS"]:
            impact = estimate_impact(product, row)
            self.assertEqual(impact["status"], "OK")
            co2e = next(metric for metric in impact["metrics"] if metric["metric"] == "CO2E_KG")
            self.assertLessEqual(co2e["low"], co2e["central"])
            self.assertLessEqual(co2e["central"], co2e["high"])
            self.assertTrue(impact["assumptions"])
            self.assertTrue(impact["factors"])
            for factor in impact["factors"]:
                self.assertTrue(factor["factor_id"])
                self.assertIsNotNone(factor["source_year"])

    def test_solar_scenario_cannot_displace_more_than_annual_use(self):
        impact = estimate_impact("SOLAR_FINANCE", pd.Series({"elec_kwh_yr": 50}))
        generation = next(metric for metric in impact["metrics"] if metric["metric"] == "ENERGY_KWH")
        self.assertLessEqual(generation["high"], 50)
        self.assertGreaterEqual(impact["scenario_kg_co2e"], 0)

    def test_missing_inputs_are_not_imputed(self):
        impact = estimate_impact("EV_FINANCE", pd.Series({"annual_mileage": None, "fuel_type_code": 1}))
        self.assertEqual(impact["status"], "INSUFFICIENT_DATA")
        self.assertEqual(impact["metrics"], [])
        self.assertIn("annual_mileage", impact["missing_inputs"])


if __name__ == "__main__":
    unittest.main()
