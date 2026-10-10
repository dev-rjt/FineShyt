from pathlib import Path
import unittest

import pandas as pd


ROOT = Path("data")


class DatasetTests(unittest.TestCase):
    def test_customer_360_is_one_row_per_customer(self):
        customers = pd.read_csv(ROOT / "raw/customers.csv")
        features = pd.read_csv(ROOT / "processed/customer_360.csv")
        self.assertTrue(features["customer_id"].is_unique)
        self.assertEqual(set(features["customer_id"]), set(customers["customer_id"]))

    def test_labels_cover_all_required_products(self):
        customers = pd.read_csv(ROOT / "raw/customers.csv")
        labels = pd.read_csv(ROOT / "processed/product_takeup_labels.csv")
        products = {"EV_FINANCE", "GREEN_HOME_LOAN", "SOLAR_FINANCE", "PAPERLESS_BANKING"}
        self.assertEqual(set(labels["product_code"]), products)
        self.assertEqual(len(labels), len(customers) * len(products))
        self.assertFalse(labels[["customer_id", "product_code"]].duplicated().any())

    def test_feature_dates_do_not_cross_cutoff(self):
        cutoff = pd.Timestamp("2026-06-30")
        tx = pd.read_csv(ROOT / "raw/transactions.csv", parse_dates=["transaction_date"])
        energy = pd.read_csv(ROOT / "raw/energy_usage.csv", parse_dates=["month"])
        digital = pd.read_csv(ROOT / "raw/digital_usage.csv", parse_dates=["month"])
        self.assertLessEqual(tx["transaction_date"].max(), cutoff)
        self.assertLessEqual(energy["month"].max(), cutoff)
        self.assertLessEqual(digital["month"].max(), cutoff)

    def test_customer_splits_are_disjoint_and_complete(self):
        customers = set(pd.read_csv(ROOT / "raw/customers.csv")["customer_id"])
        train = set(pd.read_csv(ROOT / "splits/train_customers.csv")["customer_id"])
        validation = set(pd.read_csv(ROOT / "splits/validation_customers.csv")["customer_id"])
        test = set(pd.read_csv(ROOT / "splits/test_customers.csv")["customer_id"])
        self.assertFalse(train & validation)
        self.assertFalse(train & test)
        self.assertFalse(validation & test)
        self.assertEqual(train | validation | test, customers)

    def test_public_source_seeds_are_present(self):
        tx = pd.read_csv(ROOT / "raw/transactions.csv", usecols=["source_basis"])
        energy = pd.read_csv(ROOT / "raw/energy_usage.csv", usecols=["profile_source"])
        self.assertTrue((tx["source_basis"] == "UCI_ONLINE_RETAIL_II_SEEDED").any())
        self.assertTrue((energy["profile_source"] == "LONDON_SMART_METER_SEEDED").all())

    def test_future_labels_are_not_features(self):
        features = pd.read_csv(ROOT / "processed/customer_360.csv", nrows=1)
        forbidden = {"take_up", "take_up_date", "has_ev_finance", "has_green_home_loan", "has_solar_finance", "has_paperless_banking"}
        self.assertFalse(forbidden.intersection(features.columns))


if __name__ == "__main__":
    unittest.main()
