"""Seeded value-only transformations, verified before publishing any tables."""
import argparse
import csv
import os
import random
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

from responsible_ai.pii_scrubber import scrub_merchant_description
from responsible_ai.schema_guard import assert_schema_unchanged

SEED = 2026
SOURCE_FOLDERS = ("raw", "processed", "reference", "splits", "reports", "external")


def read_csv_values(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        rows = list(reader)
    if not header or len(header) != len(set(header)):
        raise ValueError("CSV has empty or duplicate header")
    if any(len(row) != len(header) for row in rows):
        raise ValueError("CSV row width differs from header")
    return header, rows


def source_files(data_root):
    root = Path(data_root).resolve()
    paths = []
    for folder in SOURCE_FOLDERS:
        for path in sorted((root / folder).rglob("*.csv")):
            if "rai" in path.relative_to(root).parts:
                continue  # This package's generated reports are not input data.
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("Source symlink or unsafe path")
            paths.append(path)
    if not paths:
        raise ValueError("No source CSV tables found")
    return paths


def build_mapping(paths, seed=SEED):
    ids = set()
    for path in paths:
        header, rows = read_csv_values(path)
        if "customer_id" in header:
            index = header.index("customer_id")
            for row in rows:
                value = row[index]
                if value and not re.fullmatch(r"C\d{5}", value, flags=re.ASCII):
                    raise ValueError("Invalid customer_id format")
                if value:
                    ids.add(value)
    ordered = sorted(ids)
    if not ordered:
        raise ValueError("No customer IDs found")
    shuffled = ordered.copy()
    random.Random(seed).shuffle(shuffled)
    # A permutation can retain fixed points. This is pseudonymisation, not
    # anonymity; the mapping and row order can enable linkage.
    return dict(zip(ordered, shuffled))


def transform_table(header, rows, mapping):
    output = []
    for original in rows:
        row = original.copy()
        for index, column in enumerate(header):
            value = row[index]
            if column == "customer_id" and value:
                row[index] = mapping[value]
            elif column == "customer_since" and value:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError("customer_since must be an ISO date")
                row[index] = parsed.replace(day=1).isoformat()
            elif column == "merchant_description":
                row[index] = scrub_merchant_description(value)
        output.append(row)
    return output


def _write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def anonymise(data_root="data", *, output_root=None,
              vault_path="responsible_ai/identity_vault.csv", seed=SEED):
    root = Path(data_root).resolve()
    output_path = Path(output_root or root / "doctored")
    vault_file = Path(vault_path)
    if output_path.is_symlink() or vault_file.is_symlink():
        raise ValueError("Output/vault cannot be symlinks")
    output = output_path.resolve()
    vault = vault_file.resolve()
    paths = source_files(root)
    # Never place outputs in a source folder or overwrite original files.
    if output == root or root.is_relative_to(output):
        raise ValueError("Output directory overlaps input root")
    if any(output.is_relative_to(root / folder) for folder in SOURCE_FOLDERS):
        raise ValueError("Output directory overlaps source folder")
    if vault == output or vault.is_relative_to(output) or vault in paths:
        raise ValueError("Identity vault overlaps data tables")
    if vault.is_relative_to(root):
        raise ValueError("Identity vault must be outside data")
    mapping = build_mapping(paths, seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    vault.parent.mkdir(parents=True, exist_ok=True)
    # Prepare the vault before publishing tables; an unwritable vault must not
    # leave new doctored tables paired with an old mapping.
    fd, temporary = tempfile.mkstemp(prefix=".identity-", dir=vault.parent)
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["original_customer_id", "pseudonymous_customer_id"])
        writer.writerows(mapping.items())
    os.chmod(temporary, 0o600)
    try:
        return _publish(root, output, vault, Path(temporary), paths, mapping, seed)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _publish(root, output, vault, temporary_vault, paths, mapping, seed):
    with tempfile.TemporaryDirectory(prefix=".rai-stage-", dir=output.parent) as temp:
        staged = Path(temp)
        for path in paths:
            header, rows = read_csv_values(path)
            changed = transform_table(header, rows, mapping)
            destination = staged / path.relative_to(root)
            _write(destination, header, changed)
            # Validate actual bytes after disk round trip, using the same reader.
            assert_schema_unchanged(path, destination, table_name=str(path.relative_to(root)))
            after_header, after_rows = read_csv_values(destination)
            if after_header != header or after_rows != changed:
                raise AssertionError("CSV round trip changed values or row order")
            mutable = {"customer_id", "customer_since", "merchant_description"}
            for before_row, after_row in zip(rows, after_rows):
                if any(before_row[i] != after_row[i]
                       for i, col in enumerate(header) if col not in mutable):
                    raise AssertionError("Unapproved value transformation")
        # Publish only after every table passes. Existing generated output is
        # moved aside and restored on failure; original source files stay intact.
        backup = staged / "previous-output"
        had_output = output.exists()
        if had_output:
            if not output.is_dir():
                raise ValueError("Output is not a directory")
            os.replace(output, backup)
        try:
            output.mkdir()
            for path in paths:
                rel = path.relative_to(root)
                target = output / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged / rel, target)
            os.replace(temporary_vault, vault)
        except BaseException:
            shutil.rmtree(output, ignore_errors=True)
            if had_output:
                os.replace(backup, output)
            raise
    return {"tables": len(paths), "customers": len(mapping), "seed": seed,
            "status": "PASS"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--vault", default="responsible_ai/identity_vault.csv")
    args = parser.parse_args()
    result = anonymise(args.data_root, seed=args.seed, vault_path=args.vault)
    print(f"anonymise: {result['tables']} tables, schema preservation PASS")


if __name__ == "__main__":
    main()
