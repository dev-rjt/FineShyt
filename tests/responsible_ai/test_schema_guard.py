import pandas as pd
import pytest

from responsible_ai.schema_guard import assert_schema_unchanged, fingerprint_schema


def frame():
    return pd.DataFrame({"customer_id": ["C00001", "C00002"],
                         "region": ["LONDON", "WALES"],
                         "annual_mileage": [100.0, None]})


def test_allowed_values_and_csv_roundtrip(tmp_path):
    before = frame()
    after = before.copy()
    after["customer_id"] = ["C00002", "C00001"]
    assert_schema_unchanged(before, after)
    path = tmp_path / "table.csv"
    before.to_csv(path, index=False)
    assert fingerprint_schema(path) == fingerprint_schema(before)


@pytest.mark.parametrize("change", ["order", "drop", "add", "dtype", "null", "enum"])
def test_reject_changes(change):
    before = frame()
    after = before.copy()
    if change == "order":
        after = after.iloc[:, ::-1]
    elif change == "drop":
        after = after.drop(columns="region")
    elif change == "add":
        after["extra"] = 1
    elif change == "dtype":
        after["annual_mileage"] = after.annual_mileage.astype("Float64")
    elif change == "null":
        after.loc[1, "annual_mileage"] = 0
    else:
        after.loc[1, "region"] = "SCOTLAND"
    with pytest.raises(AssertionError):
        assert_schema_unchanged(before, after)


def test_unused_category_preserved():
    before = pd.DataFrame({"region": pd.Categorical(["LONDON"], categories=["LONDON", "WALES"])})
    after = before.copy()
    after["region"] = after.region.cat.remove_unused_categories()
    with pytest.raises(AssertionError):
        assert_schema_unchanged(before, after)


def test_json_requires_schema_and_enforces_enum():
    schema = {"type": "object", "properties": {"status": {"enum": ["PASS", "FAIL"]}},
              "required": ["status"], "additionalProperties": False}
    assert_schema_unchanged({"status": "PASS"}, {"status": "FAIL"}, json_schema=schema)
    with pytest.raises(ValueError):
        fingerprint_schema({"status": "PASS"})
    with pytest.raises(ValueError):
        fingerprint_schema({"status": "UNKNOWN"}, json_schema=schema)
    with pytest.raises(ValueError):
        fingerprint_schema({}, json_schema=schema)


def test_null_positions_cannot_move():
    before = frame()
    after = before.copy()
    after["annual_mileage"] = [None, 100.0]
    with pytest.raises(AssertionError):
        assert_schema_unchanged(before, after)


def test_duplicate_csv_header_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("customer_id,customer_id\nC00001,C00002\n")
    with pytest.raises(ValueError):
        fingerprint_schema(path)


def test_ordered_category_order_is_part_of_schema():
    before = pd.DataFrame({"region": pd.Categorical(["LONDON"], categories=["LONDON", "WALES"], ordered=True)})
    after = before.copy()
    after["region"] = after.region.cat.reorder_categories(["WALES", "LONDON"])
    with pytest.raises(AssertionError):
        assert_schema_unchanged(before, after)
