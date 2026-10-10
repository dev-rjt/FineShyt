import unittest
import pandas as pd
from rules import eligibility_detail

def row(**overrides):
    values = dict(has_vehicle=1, fuel_type_code=0, age=40, holds_GP01=0, annual_mileage=12000,
                  home_owner=1, has_mortgage=1, holds_GP02=0, holds_GP03=0,
                  paper_share=.5, holds_GP04=0)
    values.update(overrides)
    return pd.Series(values)

class EligibilitySafetyTests(unittest.TestCase):
    def test_existing_ev_is_blocked(self):
        result = eligibility_detail(row(fuel_type_code=3), "EV_FINANCE")
        self.assertEqual(result["status"], "INELIGIBLE")
        self.assertIn("NOT_EXISTING_EV_OWNER", result["failed_rules"])

    def test_missing_mileage_requires_review(self):
        result = eligibility_detail(row(annual_mileage=float("nan")), "EV_FINANCE")
        self.assertEqual(result["status"], "MANUAL_REVIEW")
        self.assertIsNone(result["is_eligible"])
        self.assertIn("annual_mileage", result["missing_requirements"])

    def test_non_homeowner_is_blocked_for_solar(self):
        result = eligibility_detail(row(home_owner=0), "SOLAR_FINANCE")
        self.assertEqual(result["status"], "INELIGIBLE")

    def test_existing_solar_is_blocked(self):
        result = eligibility_detail(row(has_solar=True), "SOLAR_FINANCE")
        self.assertEqual(result["status"], "INELIGIBLE")
        self.assertIn("NO_EXISTING_SOLAR", result["failed_rules"])

    def test_missing_fuel_type_requires_review(self):
        result = eligibility_detail(row(fuel_type_code=float("nan")), "EV_FINANCE")
        self.assertEqual(result["status"], "MANUAL_REVIEW")
        self.assertIn("vehicle_fuel_type", result["missing_requirements"])

if __name__ == "__main__":
    unittest.main()
