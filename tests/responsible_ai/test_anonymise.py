import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from responsible_ai.anonymise import anonymise, read_csv_values
from responsible_ai.schema_guard import assert_schema_unchanged
from responsible_ai.verify_inventory import verify_inventory
from responsible_ai.canary_test import run_canary
from responsible_ai.features_loader import ALLOWED_FEATURES


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def dataset(tmp_path):
    root = tmp_path / "data"
    write(root / "raw/customers.csv", ["customer_id", "customer_since", "age_band"],
          [["C00001", "2022-08-22", "25-34"], ["C00002", "2016-03-06", "45-54"]])
    write(root / "raw/transactions.csv", ["customer_id", "merchant_description", "amount"],
          [["C00002", "FASTER PAYMENT JOHN SMITH", "10.00"],
           ["C00001", "OCTOPUS ENERGY GAS 4043", "20.50"]])
    for folder in ("processed", "splits", "external/samples", "reference", "reports"):
        write(root / folder / "ids.csv", ["customer_id"], [["C00002"], ["C00001"]])
    return root


def test_global_mapping_roundtrip_and_originals(tmp_path):
    root = dataset(tmp_path)
    originals = {p: p.read_bytes() for p in root.rglob("*.csv")}
    vault = tmp_path / "vault.csv"
    result = anonymise(root, vault_path=vault, seed=11)
    assert result["status"] == "PASS"
    pairs = pd.read_csv(vault)
    mapping = dict(zip(pairs.original_customer_id, pairs.pseudonymous_customer_id))
    assert set(mapping) == set(mapping.values())
    assert len(set(mapping.values())) == 2
    assert vault.stat().st_mode & 0o777 == 0o600
    for path, original_bytes in originals.items():
        assert path.read_bytes() == original_bytes
        destination = root / "doctored" / path.relative_to(root)
        assert_schema_unchanged(path, destination)
        header, before = read_csv_values(path)
        _, after = read_csv_values(destination)
        i = header.index("customer_id")
        assert [row[i] for row in after] == [mapping[row[i]] for row in before]
    customers = pd.read_csv(root / "doctored/raw/customers.csv")
    assert customers.customer_since.tolist() == ["2022-08-01", "2016-03-01"]
    assert "JOHN SMITH" not in (root / "doctored/raw/transactions.csv").read_text()
    assert "10.00" in (root / "doctored/raw/transactions.csv").read_text()
    snapshot = {p.relative_to(root / "doctored"): p.read_bytes()
                for p in (root / "doctored").rglob("*.csv")}
    anonymise(root, vault_path=vault, seed=11)
    assert snapshot == {p.relative_to(root / "doctored"): p.read_bytes()
                        for p in (root / "doctored").rglob("*.csv")}


def test_invalid_id_and_date_do_not_publish(tmp_path):
    root = dataset(tmp_path)
    path = root / "raw/customers.csv"
    path.write_text(path.read_text().replace("C00001", "INVALID"))
    with pytest.raises(ValueError, match="customer_id"):
        anonymise(root, vault_path=tmp_path / "vault.csv")
    assert not (root / "doctored").exists()
    root = dataset(tmp_path)
    path.write_text(path.read_text().replace("2022-08-22", "2022-99-22"))
    with pytest.raises(ValueError):
        anonymise(root, vault_path=tmp_path / "vault.csv")
    assert not (root / "doctored").exists()


def test_unsafe_destinations(tmp_path):
    root = dataset(tmp_path)
    with pytest.raises(ValueError):
        anonymise(root, output_root=root / "raw", vault_path=tmp_path / "vault.csv")
    with pytest.raises(ValueError):
        anonymise(root, vault_path=root / "vault.csv")


def test_inventory_reports_tampering_missing_and_counts(tmp_path):
    root = dataset(tmp_path)
    path = root / "raw/customers.csv"
    inventory = tmp_path / "inventory.csv"
    write(inventory, ["file", "rows", "columns", "size_bytes", "sha256"], [[
        str(path.relative_to(tmp_path)), 2, 3, path.stat().st_size,
        hashlib.sha256(path.read_bytes()).hexdigest()]])
    assert verify_inventory(tmp_path, inventory)[0]["status"] == "PASS"
    path.write_text(path.read_text() + "C00003,2020-01-01,55-64\n")
    result = verify_inventory(tmp_path, inventory)[0]
    assert {"SHA256_MISMATCH", "SIZE_MISMATCH", "ROW_COUNT_MISMATCH"} <= set(result["mismatches"])
    path.unlink()
    assert verify_inventory(tmp_path, inventory)[0]["mismatches"] == ["MISSING_FILE"]


def test_canary_runs_anonymiser_and_feature_outputs(tmp_path):
    root = dataset(tmp_path)
    # Tiny synthetic fixture only; no production dataset is generated.
    columns = {name: [0.5, 0.8] for name in ALLOWED_FEATURES["customer_360"]}
    columns.update({"customer_id": ["C00001", "C00002"],
                    "region": ["LONDON", "WALES"],
                    "property_type": ["FLAT", "DETACHED"],
                    "vehicle_fuel_type": ["PETROL", "DIESEL"]})
    pd.DataFrame(columns).to_csv(root / "processed/customer_360.csv", index=False)
    path = root / "raw/transactions.csv"
    table = pd.read_csv(path)
    table["debit_credit"] = "DEBIT"
    table.to_csv(path, index=False)
    original = path.read_bytes()
    record = tmp_path / "records.json"
    record.write_text('{}')
    result = run_canary(root, records_path=record)
    assert result["status"] == "PASS" and result["record_scan"] == "SCANNED"
    assert path.read_bytes() == original


def test_guard_failure_keeps_previous_output(tmp_path, monkeypatch):
    root = dataset(tmp_path)
    vault = tmp_path / "vault.csv"
    anonymise(root, vault_path=vault)
    output = root / "doctored/raw/customers.csv"
    before = output.read_bytes()
    def reject(*args, **kwargs):
        raise AssertionError("Guard rejected")
    monkeypatch.setattr("responsible_ai.anonymise.assert_schema_unchanged", reject)
    with pytest.raises(AssertionError):
        anonymise(root, vault_path=vault)
    assert output.read_bytes() == before
