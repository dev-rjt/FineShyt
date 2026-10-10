import os
import unittest

from fastapi import HTTPException

from api import LoginRequest, get_customer, get_feature_weights, get_opportunities, health, login


class ApiIntegrationTests(unittest.TestCase):
    def login(self, username, password):
        return login(LoginRequest(username=username, password=password))["principal"]

    def test_health_describes_complete_stack(self):
        body = health()
        self.assertEqual(body["customers"], 5000)
        self.assertEqual(body["opportunity_records"], 20000)
        self.assertEqual(body["components"]["backend"], "fastapi")
        self.assertEqual(body["components"]["impact"], "deterministic_carbon_engine")

    def test_customer_is_scoped_to_own_live_score(self):
        principal = self.login(os.environ["CUSTOMER_DEMO_ID"], os.environ["CUSTOMER_DEMO_PASSWORD"])
        customer_id = os.environ["CUSTOMER_DEMO_ID"]
        own = get_opportunities(customer_id, principal)
        self.assertEqual(len(own["items"]), 4)
        self.assertEqual(own["scoring_source"], "live_model")
        with self.assertRaises(HTTPException) as caught:
            get_opportunities("C10001", principal)
        self.assertEqual(caught.exception.status_code, 403)

    def test_bank_can_access_portfolio_and_customer(self):
        principal = self.login(os.environ["BANK_DEMO_ID"], os.environ["BANK_DEMO_PASSWORD"])
        weights = get_feature_weights("EV_FINANCE", principal)
        self.assertGreater(len(weights["items"]), 5)
        customer = get_opportunities("C12558", principal)
        self.assertEqual(len(customer["items"]), 4)
        self.assertEqual(get_customer("C12558", principal)["customer_id"], "C12558")


if __name__ == "__main__":
    unittest.main()
