"""Read-only reproducibility checks; missing inventory entries fail closed."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def verify_inventory(root, inventory):
    root = Path(root).resolve()
    results = []
    with Path(inventory).open(newline="", encoding="utf-8") as stream:
        entries = list(csv.DictReader(stream))
    required = {"file", "rows", "columns", "sha256", "size_bytes"}
    if not entries or not required <= set(entries[0]):
        raise ValueError("Inventory missing required columns or entries")
    if len({entry["file"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate inventory paths")
    for entry in entries:
        relative = Path(entry["file"])
        path = (root / relative).resolve()
        mismatches = []
        if relative.is_absolute() or not path.is_relative_to(root):
            mismatches.append("UNSAFE_PATH")
        elif not path.is_file():
            mismatches.append("MISSING_FILE")
        else:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                mismatches.append("SHA256_MISMATCH")
            if path.stat().st_size != int(entry["size_bytes"]):
                mismatches.append("SIZE_MISMATCH")
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.reader(stream)
                header = next(reader, [])
                rows = 0
                malformed = False
                for row in reader:
                    rows += 1
                    malformed |= len(row) != len(header)
            if rows != int(entry["rows"]):
                mismatches.append("ROW_COUNT_MISMATCH")
            if len(header) != int(entry["columns"]):
                mismatches.append("COLUMN_COUNT_MISMATCH")
            if len(header) != len(set(header)) or malformed:
                mismatches.append("MALFORMED_CSV")
        results.append({"file": entry["file"],
                        "status": "FAIL" if mismatches else "PASS",
                        "mismatches": mismatches})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--inventory", default="file_inventory.csv")
    parser.add_argument("--output", default="data/reports/rai/inventory.json")
    args = parser.parse_args()
    results = verify_inventory(args.root, args.inventory)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failures = sum(row["status"] == "FAIL" for row in results)
    print(f"inventory: {len(results) - failures} PASS, {failures} FAIL")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
