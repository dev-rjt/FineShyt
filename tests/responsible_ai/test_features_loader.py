import pandas as pd
import pytest

from responsible_ai import features_loader as loader


def test_projection_scrubs_and_removes_identity_metadata():
    source = pd.DataFrame({"merchant_description": ["TFR TO A. KUMAR"],
                           "amount": [10.0], "debit_credit": ["DEBIT"],
                           "true_category": ["OTHER"], "customer_id": ["C00001"]},
                          index=["C00001"])
    source.attrs["customer_id"] = "C00001"
    result = loader.load_features(source, table_name="transactions")
    assert tuple(result.columns) == loader.ALLOWED_FEATURES["transactions"]
    assert result.iloc[0].merchant_description == "TFR TO [REDACTED]"
    assert result.index.tolist() == [0] and result.attrs == {}
    assert source.iloc[0].merchant_description == "TFR TO A. KUMAR"


@pytest.mark.parametrize("column", sorted(loader.BANNED_FOR_MODELS))
def test_all_banned_requests(column):
    with pytest.raises(ValueError, match="Banned"):
        loader.load_features(pd.DataFrame({column: [1]}),
                             table_name="customer_360", requested=[column])


def test_corrupt_config_rejected_even_if_other_table_requested(monkeypatch):
    monkeypatch.setitem(loader.ALLOWED_FEATURES, "customer_360", ("customer_id",))
    with pytest.raises(ValueError, match="contains a banned"):
        loader.load_features(pd.DataFrame(), table_name="transactions")


def test_unknown_missing_duplicate_and_empty():
    frame = pd.DataFrame({"amount": [1.0]})
    for kwargs in ({"requested": ["invented"]}, {"requested": []},
                   {"requested": ["amount", "amount"]}, {}):
        with pytest.raises(ValueError):
            loader.load_features(frame, table_name="transactions", **kwargs)
    with pytest.raises(ValueError):
        loader.load_features(frame, table_name="unknown")


def test_path_and_null_preservation(tmp_path):
    path = tmp_path / "customer_360.csv"
    pd.DataFrame({"annual_mileage": [10.0, None]}).to_csv(path, index=False)
    result = loader.load_features(path, requested=["annual_mileage"])
    assert result.annual_mileage.isna().tolist() == [False, True]


def test_income_default_banned():
    assert loader.BAN_INCOME_FOR_MODELS
    assert "income_band" in loader.BANNED_FOR_MODELS
