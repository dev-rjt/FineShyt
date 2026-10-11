import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from auth import (
    authenticate,
    create_local_demo_env,
    credentials_ready,
    hash_password,
    initialize_local_demo_env,
    load_local_env,
    verify_password,
)


class AuthTests(unittest.TestCase):
    ENV = {
        "BANK_DEMO_ID": "bank_manager",
        "BANK_DEMO_PASSWORD_HASH": hash_password("bank-secret"),
        "CUSTOMER_DEMO_ID": "C12558",
        "CUSTOMER_DEMO_PASSWORD_HASH": hash_password("customer-secret"),
        "APP_SESSION_SECRET": "test-session-secret-with-more-than-24-chars",
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
            self.assertIsNone(authenticate("bank_manager", " bank-secret "))
            self.assertIsNone(authenticate("C12558", "wrong"))
            self.assertIsNone(authenticate("unknown", "bank-secret"))

    def test_credentials_must_all_be_present(self):
        with patch.dict(os.environ, self.ENV, clear=True):
            self.assertTrue(credentials_ready())
        incomplete = {**self.ENV, "APP_SESSION_SECRET": "short"}
        with patch.dict(os.environ, incomplete, clear=True):
            self.assertFalse(credentials_ready())

    def test_plaintext_environment_passwords_are_rejected(self):
        legacy_env = {
            "BANK_DEMO_ID": "bank_manager",
            "BANK_DEMO_PASSWORD": "bank-secret",
            "CUSTOMER_DEMO_ID": "C12558",
            "CUSTOMER_DEMO_PASSWORD": "customer-secret",
            "APP_SESSION_SECRET": self.ENV["APP_SESSION_SECRET"],
        }
        with patch.dict(os.environ, legacy_env, clear=True):
            self.assertFalse(credentials_ready())
            self.assertIsNone(authenticate("bank_manager", "bank-secret"))

    def test_local_demo_env_uses_unique_credentials_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            credentials = create_local_demo_env(path)

            self.assertIsNotNone(credentials)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            contents = path.read_text(encoding="utf-8")
            env_values = dict(line.split("=", 1) for line in contents.splitlines())
            self.assertNotIn(credentials[0], contents)
            self.assertNotIn(credentials[1], contents)
            self.assertTrue(verify_password(credentials[0], env_values["BANK_DEMO_PASSWORD_HASH"]))
            self.assertTrue(verify_password(credentials[1], env_values["CUSTOMER_DEMO_PASSWORD_HASH"]))
            self.assertNotEqual(env_values["BANK_DEMO_PASSWORD_HASH"], env_values["CUSTOMER_DEMO_PASSWORD_HASH"])
            self.assertGreaterEqual(len(env_values["APP_SESSION_SECRET"]), 24)
            self.assertIsNone(create_local_demo_env(path))

    def test_legacy_local_passwords_are_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "BANK_DEMO_ID=bank_manager\nBANK_DEMO_PASSWORD=bank-secret\n"
                "CUSTOMER_DEMO_ID=C12558\nCUSTOMER_DEMO_PASSWORD=customer-secret\n"
                "APP_SESSION_SECRET=test-session-secret-with-more-than-24-chars\n",
                encoding="utf-8",
            )

            credentials = initialize_local_demo_env(path)
            contents = path.read_text(encoding="utf-8")
            env_values = dict(line.split("=", 1) for line in contents.splitlines())

            self.assertEqual(credentials, ("bank-secret", "customer-secret"))
            self.assertNotIn("BANK_DEMO_PASSWORD=", contents)
            self.assertNotIn("CUSTOMER_DEMO_PASSWORD=", contents)
            self.assertTrue(verify_password("bank-secret", env_values["BANK_DEMO_PASSWORD_HASH"]))
            self.assertTrue(verify_password("customer-secret", env_values["CUSTOMER_DEMO_PASSWORD_HASH"]))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

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
