"""Batch runner for complete contract JSON objects, lists or JSONL records."""

import argparse
import json
from pathlib import Path
import sys

from .engine import ExplanationEngine
from .providers import OllamaProvider
from .verifier import strict_json_loads


def read_records(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        records = [strict_json_loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = strict_json_loads(text)
        records = data if isinstance(data, list) else [data]
    if not records or any(not isinstance(record, dict) for record in records):
        raise ValueError("Expected complete contract object records")
    return records


def write_records(path, records):
    path = Path(path)
    if path.exists():
        raise ValueError("Output already exists; choose a new path")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ("\n".join(json.dumps(record, allow_nan=False) for record in records) + "\n") if path.suffix == ".jsonl" else (
        json.dumps(records[0] if len(records) == 1 else records, indent=2, allow_nan=False) + "\n")
    # Exclusive creation also protects against a file appearing after the check.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate checked customer and bank-staff explanations")
    parser.add_argument("--records", required=True, help="Full contract JSON/JSONL input")
    parser.add_argument("--output", required=True, help="New JSON/JSONL output path")
    parser.add_argument("--provider", choices=("template", "ollama"), default="template")
    parser.add_argument("--require-llm", action="store_true", help="Exit nonzero if any visible explanation uses a fallback")
    args = parser.parse_args(argv)
    try:
        if Path(args.records).resolve() == Path(args.output).resolve():
            raise ValueError("Input and output paths must differ")
        provider = OllamaProvider.from_env() if args.provider == "ollama" else None
        engine = ExplanationEngine(provider)
        outputs = [engine.generate(record) for record in read_records(args.records)]
        write_records(args.output, outputs)
    except (ValueError, OSError):
        # Details of malformed inputs or provider configuration can include PII.
        print("LLM run failed: check configuration, complete input contract and new output path.", file=sys.stderr)
        return 1
    counts = {name: sum(record["explanation"]["status"] == name for record in outputs)
              for name in ("VERIFIED", "FALLBACK_USED", "NOT_GENERATED")}
    print(json.dumps({"records": len(outputs), **counts}))
    return int(args.require_llm and counts["FALLBACK_USED"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
