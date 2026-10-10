"""Build the local SQLite database from the versioned synthetic CSV sources."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import sqlite3
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "db" / "verdant_demo.sqlite3"
SCHEMA = ROOT / "db" / "schema.sql"
DATA = ROOT / "product_app" / "data"
OUTPUTS = ROOT / "product_app" / "outputs"

SOURCES = [
    ("customers", DATA / "customers.csv", {}),
    ("green_products", DATA / "green_products.csv", {"product": "product_name"}),
    ("emission_factors", DATA / "emissions_factors.csv", {}),
    ("model_assumptions", DATA / "model_assumptions.csv", {}),
    ("customer_products", DATA / "products.csv", {}),
    ("bank_transactions", DATA / "transactions.csv", {"date": "transaction_date"}),
    ("vehicles", DATA / "vehicles.csv", {}),
    ("energy_usage", DATA / "energy_usage.csv", {}),
    ("digital_usage", DATA / "digital_usage.csv", {}),
    ("customer_features", DATA / "customer_360.csv", {}),
    ("recommendations", OUTPUTS / "recommendations_all.csv", {}),
]


def normalise(value: str):
    if value == "":
        return None
    lowered = value.lower()
    if lowered == "true":
        return 1
    if lowered == "false":
        return 0
    return value


def load_csv(connection: sqlite3.Connection, table: str, path: Path, rename: dict[str, str]) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        source_columns = reader.fieldnames or []
        columns = [rename.get(column, column) for column in source_columns]
        quoted = ", ".join(f'"{column}"' for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        statement = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
        rows = ([normalise(row[column]) for column in source_columns] for row in reader)
        cursor = connection.executemany(statement, rows)
        return cursor.rowcount


def build(database: Path = DEFAULT_DATABASE, quiet: bool = False) -> Path:
    database.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="verdant-", suffix=".sqlite3", dir=database.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        counts = {}
        with connection:
            for table, path, rename in SOURCES:
                counts[table] = load_csv(connection, table, path, rename)
            connection.execute(
                "INSERT INTO schema_metadata(schema_version, dataset_name, customer_count) VALUES (?, ?, ?)",
                ("1.0.0", "Verdant synthetic banking demo", counts["customers"]),
            )
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"Foreign-key validation failed: {violations[:5]}")
        connection.close()
        os.replace(temporary, database)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    if not quiet:
        print(f"Built {database}")
        for table, count in counts.items():
            print(f"  {table}: {count:,} rows")
    return database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    build(args.database, args.quiet)


if __name__ == "__main__":
    main()
