"""Strict before/after guards; CSV has observed, not declared, nullability."""
from __future__ import annotations

import hashlib
import json
import csv
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

# Identifiers, dates and free text are not categorical domains. Other object
# columns are conservatively categorical; never infer enums from examples.
VALUE_COLUMNS = frozenset({
    "customer_id", "transaction_id", "vehicle_id", "customer_product_id",
    "factor_id", "product_id", "source_customer_key", "source_household_key",
    "customer_since", "transaction_date", "month", "record_date",
    "data_cutoff_date", "cutoff_date", "take_up_date", "start_date", "end_date",
    "source_month", "invoice_date", "merchant_description", "description",
    "detail", "source", "intended_use", "product_name",
})


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _shape(value):
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        # Preserve array element structures, without treating length as schema.
        return sorted({json.dumps(_shape(item), sort_keys=True) for item in value})
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    raise TypeError("Non-JSON value")


def fingerprint_schema(table, *, json_schema=None, table_name=None):
    """Accept a DataFrame, CSV path, or JSON object/list with explicit schema.

    CSV checks exact dtypes, column order, observed null positions, and complete
    categorical domains. CSV cannot encode a declared nullable constraint.
    JSON checks the supplied schema plus observed structure; null transitions
    are conservatively treated as structural changes. No payload is returned.
    """
    if isinstance(table, (str, Path)):
        with Path(table).open(newline="", encoding="utf-8") as stream:
            header = next(csv.reader(stream), [])
        if not header or len(header) != len(set(header)):
            raise ValueError("Empty or duplicate CSV header")
        table = pd.read_csv(table)
    if isinstance(table, pd.DataFrame):
        if not table.columns.is_unique:
            raise ValueError("Duplicate columns are not supported")
        columns = []
        for name, series in table.items():
            categorical = isinstance(series.dtype, pd.CategoricalDtype)
            domain = None
            if categorical or (name not in VALUE_COLUMNS and
                               (pd.api.types.is_object_dtype(series.dtype) or
                                pd.api.types.is_string_dtype(series.dtype))):
                values = series.cat.categories if categorical else series.dropna().unique()
                entries = [(type(v).__name__, str(v)) for v in values]
                domain = _digest(entries if categorical and series.cat.ordered
                                 else sorted(entries))
            columns.append({
                "name": name, "dtype": str(series.dtype),
                "nullable_observed": bool(series.isna().any()),
                "null_positions": _digest(series.isna().tolist()),
                "domain": domain,
                "ordered": bool(series.cat.ordered) if categorical else None,
            })
        return {"kind": "csv", "table": table_name, "columns": columns}
    if not isinstance(table, (Mapping, list)) or json_schema is None:
        raise ValueError("JSON records require an explicit JSON Schema")
    _digest(table)  # Reject NaN/Infinity, which Python can otherwise accept as JSON.
    Draft202012Validator.check_schema(json_schema)
    validator = Draft202012Validator(json_schema, format_checker=FormatChecker())
    records = table if isinstance(table, list) else [table]
    for record in records:
        if not validator.is_valid(record):
            # jsonschema exception messages can contain entire payloads.
            raise ValueError("JSON record violates supplied schema")
    return {"kind": "json", "table": table_name,
            "schema": _digest(json_schema), "structure": _digest(_shape(table))}


def assert_schema_unchanged(before, after, **kwargs):
    """Raise without exposing values; pass snapshots of tables, not fingerprints."""
    if fingerprint_schema(before, **kwargs) != fingerprint_schema(after, **kwargs):
        raise AssertionError("Schema changed: columns, dtype, nulls, domain or structure")
