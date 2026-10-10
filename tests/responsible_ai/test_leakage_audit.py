import pandas as pd
import pytest

from responsible_ai.leakage_audit import (
    audit_dates, audit_feature_tables, audit_labels, audit_splits, run_audit,
)


def customers():
    return pd.DataFrame({"customer_id": [f"C{i:05d}" for i in range(1, 7)],
                         "data_cutoff_date": ["2026-06-30"] * 6})


def labels():
    return pd.DataFrame({"customer_id": customers().customer_id,
                         "product_code": ["EV_FINANCE"] * 6,
                         "cutoff_date": ["2026-06-30"] * 6,
                         "outcome_window_days": [90] * 6,
                         "take_up": [0, 1, 0, 1, 0, 1],
                         "take_up_date": [None, "2026-07-01", None, "2026-09-28", None, "2026-08-01"],
                         "label_method": ["LATENT_FACTORS_PLUS_NOISE_V1"] * 6})


def test_banned_feature_detected():
    assert audit_feature_tables({"bad": pd.DataFrame({"customer_id": []})})[0]["status"] == "FAIL"


def test_disjoint_coverage_duplicates_and_wrong_split():
    c = customers()
    s = {name: pd.DataFrame({"customer_id": c.customer_id.iloc[i:i + 2].tolist(), "split": [name] * 2})
         for name, i in [("TRAIN", 0), ("VALIDATION", 2), ("TEST", 4)]}
    assert audit_splits(c, s)["status"] == "PASS"
    for mutation in ("overlap", "missing", "duplicate", "wrong"):
        changed = {k: v.copy() for k, v in s.items()}
        if mutation == "overlap": changed["TEST"].loc[0, "customer_id"] = "C00001"
        if mutation == "missing": changed["TEST"] = changed["TEST"].iloc[:1]
        if mutation == "duplicate": changed["TEST"] = pd.concat([changed["TEST"]] * 2)
        if mutation == "wrong": changed["TEST"]["split"] = "TRAIN"
        assert audit_splits(c, changed)["status"] == "FAIL"


@pytest.mark.parametrize("field", ["transaction_date", "month", "record_date"])
@pytest.mark.parametrize("bad", ["2026-07-01", "invalid", None])
def test_future_invalid_missing_dates(field, bad):
    table = pd.DataFrame({"customer_id": ["C00001"], field: [bad]})
    assert audit_dates(customers(), {"raw": table})[0]["status"] == "FAIL"


def test_valid_label_window_and_correlation():
    feature = pd.DataFrame({"annual_mileage": [1, 2, 3, 4, 5, 6]})
    results, correlations = audit_labels(labels(), customers(), feature)
    assert all(r["status"] == "PASS" for r in results)
    assert correlations[0]["correlation"] is not None
    copied = pd.DataFrame({"annual_mileage": labels().take_up})
    results, _ = audit_labels(labels(), customers(), copied)
    assert any(r["check"].startswith("label_feature_copy") and r["status"] == "FAIL" for r in results)
    inverse = pd.DataFrame({"annual_mileage": 1 - labels().take_up})
    results, _ = audit_labels(labels(), customers(), inverse)
    assert any(r["status"] == "FAIL" for r in results)


@pytest.mark.parametrize("field,value", [
    ("take_up_date", "2026-06-30"), ("take_up_date", "2026-09-29"),
    ("take_up_date", None), ("label_method", None), ("label_method", ""),
    ("outcome_window_days", -1), ("take_up", 2),
])
def test_bad_labels(field, value):
    bad = labels()
    bad.loc[1, field] = value
    result, _ = audit_labels(bad, customers(), pd.DataFrame({"annual_mileage": range(6)}))
    assert any(r["status"] == "FAIL" for r in result)


def test_missing_inputs_fail_instead_of_skip(tmp_path):
    results, _ = run_audit(tmp_path)
    assert results and all(r["status"] == "FAIL" for r in results)
