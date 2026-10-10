"""Append-only, allowlisted API decision metadata. No explanations or payloads."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from responsible_ai.contract_checks import load_records, validate_record

VERSION_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_id: str = Field(pattern=r"^rai-[a-f0-9]{32}$")
    customer_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")
    product_id: str = Field(pattern=r"^GP0[1-6]$")
    opportunity: str
    opportunity_status: str
    impact_status: str
    gate_pass: bool
    insight_source: str | None
    model_version: str
    rule_version: str
    factor_ids: list[str]
    data_as_of: str
    timestamp: str


def append_audit(record, path="data/reports/rai/audit.jsonl", *, allow_stub_placeholders=False):
    if validate_record(record, allow_stub_placeholders=allow_stub_placeholders):
        raise ValueError("Refusing invalid API opportunity; no payload logged")
    tokens = [record["model_version"], record["gate"]["rule_version"]]
    factor_ids = sorted({factor["factor_id"] for factor in record["impact"]["factors"]})
    if any(not VERSION_TOKEN.fullmatch(value) for value in tokens + factor_ids):
        raise ValueError("Invalid version or factor token; no payload logged")
    try:
        entry = _entry(record, factor_ids)
    except ValidationError:
        raise ValueError("Invalid audit metadata; no payload logged") from None
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("Audit log cannot be a symlink")
    import fcntl

    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(entry.model_dump_json() + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return entry.model_dump()


def _entry(record, factor_ids):
    insight = record["insight"]
    return AuditEntry(
        event_id="rai-" + uuid.uuid4().hex,
        customer_id=record["customer_id"],
        product_id=record["product_id"],
        opportunity=record["opportunity"],
        opportunity_status=record["status"],
        impact_status=record["impact"]["status"],
        gate_pass=record["gate"]["rule_pass"],
        insight_source=insight["source"] if insight else None,
        model_version=record["model_version"],
        rule_version=record["gate"]["rule_version"],
        factor_ids=factor_ids,
        data_as_of=record["data_as_of"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True)
    parser.add_argument("--output", default="data/reports/rai/audit.jsonl")
    parser.add_argument("--allow-stub-placeholders", action="store_true")
    args = parser.parse_args()
    records = load_records(args.records)
    if any(validate_record(record, allow_stub_placeholders=args.allow_stub_placeholders) for record in records):
        print("audit_log: FAIL")
        return 1
    for record in records:
        append_audit(record, args.output, allow_stub_placeholders=args.allow_stub_placeholders)
    print("audit_log: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
