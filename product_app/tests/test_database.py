import unittest

from api_service import connection, data_catalog, repository


class DatabaseIntegrationTests(unittest.TestCase):
    def test_expected_business_tables_and_counts_are_present(self):
        catalog = {item["name"]: item for item in data_catalog()["tables"]}
        self.assertEqual(catalog["customers"]["rows"], 5000)
        self.assertEqual(catalog["bank_transactions"]["rows"], 684202)
        self.assertEqual(catalog["recommendations"]["rows"], 20000)
        self.assertEqual(catalog["customer_portfolio"]["rows"], 5000)

    def test_database_foreign_keys_are_clean(self):
        with connection() as database:
            self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_backend_repository_reads_boolean_recommendations(self):
        recommendations = repository()["recommendations"]
        self.assertEqual(str(recommendations["recommend"].dtype), "bool")


if __name__ == "__main__":
    unittest.main()
