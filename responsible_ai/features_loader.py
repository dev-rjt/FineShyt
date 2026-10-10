"""Fail-closed feature projection. No imputation, encoding, training or rules."""
from pathlib import Path
import csv

import pandas as pd

from responsible_ai.pii_scrubber import scrub_merchant_description

# ML owner must confirm before enabling income; retain for bias audit separately.
BAN_INCOME_FOR_MODELS = True
BANNED_FOR_MODELS = frozenset({
    "true_category", "customer_archetype", "record_source", "source_basis",
    "profile_source", "label_method", "take_up", "take_up_date", "age_band",
    "postcode_area", "customer_id",
} | ({"income_band"} if BAN_INCOME_FOR_MODELS else set()))

# Candidate inputs only, copied from the authoritative dictionary. Inclusion
# is not evidence of point-in-time safety or absence of proxy bias.
ALLOWED_FEATURES = {
    "customer_360": (
        "region", "home_owner", "property_type", "mortgage_customer",
        "stated_sustainability_preference", "digital_preference",
        "automotive_spend_6m", "electricity_spend_6m", "fuel_spend_6m",
        "gas_spend_6m", "home_improvement_spend_6m", "other_spend_6m",
        "public_transport_spend_6m", "utilities_spend_6m", "transaction_count_6m",
        "total_spend_6m", "has_vehicle", "vehicle_fuel_type", "vehicle_age_years",
        "annual_mileage", "has_existing_ev", "average_monthly_electricity_kwh",
        "average_monthly_gas_kwh", "energy_data_months", "has_solar",
        "average_mobile_logins_3m", "average_digital_transactions_3m",
        "average_branch_visits_3m", "paper_statements_active",
        "average_email_open_rate", "digital_data_months", "has_current_account",
        "has_investment_account", "has_mortgage", "has_personal_loan",
        "has_savings_account", "has_vehicle_loan", "vehicle_data_available",
        "energy_data_available", "digital_data_available",
        "conflicting_homeownership_signal", "data_completeness",
    ),
    "transactions": ("merchant_description", "amount", "debit_credit"),
}
if not BAN_INCOME_FOR_MODELS:
    ALLOWED_FEATURES["customer_360"] += ("income_band",)


def validate_feature_config():
    for columns in ALLOWED_FEATURES.values():
        if BANNED_FOR_MODELS.intersection(columns):
            raise ValueError("ALLOWED_FEATURES contains a banned column")
        if len(columns) != len(set(columns)):
            raise ValueError("Duplicate configured features")


def load_features(table, *, table_name=None, requested=None):
    """Project a CSV path or DataFrame; DataFrames require table_name.

    All configured features are required by default. An explicit requested
    subset is supported. Unknown requests fail; missing values remain missing.
    Raw metadata/labels can exist in input, but never enter the returned frame.
    """
    validate_feature_config()
    if isinstance(table, (str, Path)):
        table_name = table_name or Path(table).stem
        with Path(table).open(newline="", encoding="utf-8") as stream:
            header = next(csv.reader(stream), [])
        if not header or len(header) != len(set(header)):
            raise ValueError("Empty or duplicate input columns")
        table = pd.read_csv(table)
    if not isinstance(table, pd.DataFrame):
        raise TypeError("Expected a DataFrame or CSV path")
    if table_name not in ALLOWED_FEATURES:
        raise ValueError("Unsupported feature table")
    if not table.columns.is_unique:
        raise ValueError("Duplicate input columns")
    if isinstance(requested, str):
        raise TypeError("requested must be a sequence of column names")
    selected = tuple(ALLOWED_FEATURES[table_name] if requested is None else requested)
    if BANNED_FOR_MODELS.intersection(selected):
        raise ValueError("Banned model feature requested")
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Features must be nonempty and unique")
    if set(selected) - set(ALLOWED_FEATURES[table_name]):
        raise ValueError("Feature is not explicitly allowed")
    if set(selected) - set(table.columns):
        raise ValueError("Required feature columns missing")
    result = table.loc[:, list(selected)].copy(deep=True)
    if "merchant_description" in result:
        result["merchant_description"] = result["merchant_description"].map(
            scrub_merchant_description)
    # Avoid passing identity-bearing metadata through pandas attrs/index.
    result.attrs = {}
    return result.reset_index(drop=True)


validate_feature_config()
