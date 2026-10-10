import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from auth import authenticate, credentials_ready, load_local_env


class AuthTests(unittest.TestCase):
    ENV = {
        "BANK_DEMO_ID": "bank_manager",
        "BANK_DEMO_PASSWORD": "bank-secret",
        "CUSTOMER_DEMO_ID": "C12558",
        "CUSTOMER_DEMO_PASSWORD": "customer-secret",
    }

    def test_bank_and_customer_are_separate_principals(self):
        with patch.dict(os.environ, self.ENV, clear=True):
            bank = authenticate("bank_manager", "bank-secret")
            customer = authenticate("c12558", "customer-secret")
            self.assertEqual(bank.role, "bank")
            self.assertEqual(customer.role, "customer")
            self.assertEqual(customer.customer_id, "C12558")
            self.assertIsNone(bank.customer_id)

    def test_invalid_credentials_are_rejected(self):
        with patch.dict(os.environ, self.ENV, clear=True):
            self.assertIsNone(authenticate("bank_manager", "wrong"))
            self.assertIsNone(authenticate("C12558", "wrong"))
            self.assertIsNone(authenticate("unknown", "bank-secret"))

    def test_credentials_must_all_be_present(self):
        with patch.dict(os.environ, self.ENV, clear=True):
            self.assertTrue(credentials_ready())
        with patch.dict(os.environ, {"BANK_DEMO_ID": "bank_manager"}, clear=True):
            self.assertFalse(credentials_ready())

    def test_local_env_does_not_override_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("BANK_DEMO_ID=file-value\nCUSTOMER_DEMO_ID='C12558'\n", encoding="utf-8")
            with patch.dict(os.environ, {"BANK_DEMO_ID": "shell-value"}, clear=True):
                load_local_env(path)
                self.assertEqual(os.environ["BANK_DEMO_ID"], "shell-value")
                self.assertEqual(os.environ["CUSTOMER_DEMO_ID"], "C12558")


if __name__ == "__main__":
    unittest.main()
