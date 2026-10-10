"""Contextual privacy canary in an isolated copy; never modifies original data."""
import argparse
import json
import shutil
import tempfile
from pathlib import Path

from responsible_ai.anonymise import anonymise, read_csv_values, source_files, _write
from responsible_ai.features_loader import ALLOWED_FEATURES, load_features
from responsible_ai.schema_guard import assert_schema_unchanged

CANARY = "ZZ TESTNAME"


def assert_no_canary(paths, token=CANARY):
    markers = [token.encode("utf-8"), token.encode("utf-16-le"), token.encode("utf-16-be")]
    for candidate in paths:
        path = Path(candidate)
        if not path.exists():
            raise ValueError("Required canary scan input missing")
        files = path.rglob("*") if path.is_dir() else [path]
        for file in files:
            if file.is_file():
                data = file.read_bytes()
                if any(marker in data for marker in markers):
                    raise AssertionError("CANARY_LEAK: token found in scanned output")
                if file.suffix in {".json", ".jsonl"}:
                    try:
                        objects = ([json.loads(line) for line in data.decode().splitlines() if line.strip()]
                                   if file.suffix == ".jsonl" else json.loads(data))
                        if token in json.dumps(objects, ensure_ascii=False):
                            raise AssertionError("CANARY_LEAK: decoded JSON contains token")
                    except (UnicodeError, json.JSONDecodeError):
                        raise ValueError("Invalid supplied JSON scan artifact") from None


def run_canary(data_root="data", *, scan_paths=(), records_path=None):
    root = Path(data_root).resolve()
    with tempfile.TemporaryDirectory(prefix="rai-canary-") as directory:
        temp = Path(directory)
        copied = temp / "data"
        for source in source_files(root):
            destination = copied / source.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        target = copied / "raw/transactions.csv"
        if not target.exists():
            raise ValueError("Canary needs raw/transactions.csv")
        header, rows = read_csv_values(target)
        if not rows or "merchant_description" not in header:
            raise ValueError("Canary needs a transaction description row")
        rows[0][header.index("merchant_description")] = "FASTER PAYMENT " + CANARY
        _write(target, header, rows)
        assert_schema_unchanged(root / "raw/transactions.csv", target)
        result = anonymise(copied, vault_path=temp / "identity_vault.csv")
        for before in source_files(copied):
            assert_schema_unchanged(before, copied / "doctored" / before.relative_to(copied))
        feature_dir = temp / "features"
        feature_dir.mkdir()
        for table in ALLOWED_FEATURES:
            path = copied / "doctored" / ("processed" if table == "customer_360" else "raw") / (table + ".csv")
            if not path.exists():
                raise ValueError("Canary needs every configured feature input")
            features = load_features(path)
            features.to_csv(feature_dir / (table + ".csv"), index=False)
        scans = [copied / "doctored", feature_dir, *scan_paths]
        if records_path is not None:
            scans.append(records_path)
        assert_no_canary(scans)
        return {"status": "PASS", "tables": result["tables"],
                "record_scan": "SCANNED" if records_path else "NOT_SUPPLIED",
                "limitation": "Scans supplied outputs; does not execute ML, LLM or external caches"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--records", required=True)
    parser.add_argument("--scan", action="append", default=[])
    parser.add_argument("--output", default="data/reports/rai/canary.json")
    args = parser.parse_args()
    try:
        result = run_canary(args.data_root, scan_paths=args.scan, records_path=args.records)
    except (AssertionError, ValueError, KeyError):
        result = {"status": "FAIL", "detail": "Canary leak or required input missing/invalid"}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print("canary: " + result["status"])
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
