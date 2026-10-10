"""Append-only, allowlisted audit metadata. No explanations or full payloads."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError

from responsible_ai.contract_checks import validate_record
from responsible_ai.contract_checks import load_records


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")
    customer_id: str = Field(pattern=r"^C[0-9]{5}$")
    product_code: str = Field(pattern=r"^(EV_FINANCE|GREEN_HOME_LOAN|SOLAR_FINANCE|PAPERLESS_BANKING)$")
    component_versions: dict[str, str]
    factor_version: list[str]
    statuses: dict[str, str]
    timestamp: str


def append_audit(record, path="data/reports/rai/audit.jsonl"):
    if validate_record(record):
        raise ValueError("Refusing invalid record; no payload logged")
    versions = record["audit"]["component_versions"]
    # Restrict version values to short version tokens, not arbitrary text.
    import re
    factors = sorted({factor["factor_version"] for factor in record["impact"].get("emission_factors", [])})
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value)
           for value in list(versions.values()) + factors):
        raise ValueError("Invalid version token; no payload logged")
    try:
        entry = _entry(record, versions, factors)
    except ValidationError:
        raise ValueError("Invalid audit metadata; no payload logged") from None
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("Audit log cannot be a symlink")
    # Advisory lock serialises this package's writers on Unix; not tamper-proof.
    import fcntl
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(entry.model_dump_json() + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return entry.model_dump()


def _entry(record, versions, factors):
    return AuditEntry(
        request_id=record["request_id"], customer_id=record["customer"]["customer_id"],
        product_code=record["opportunity"]["product_code"],
        component_versions=versions, factor_version=factors,
        statuses={"eligibility": record["eligibility"]["status"],
                  "recommendation": record["recommendation"]["decision"],
                  "impact": record["impact"]["status"],
                  "explanation": record["explanation"]["status"],
                  "pipeline": record["audit"]["pipeline_status"]},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True)
    parser.add_argument("--output", default="data/reports/rai/audit.jsonl")
    args = parser.parse_args()
    records = load_records(args.records)
    if any(validate_record(record) for record in records):
        print("audit_log: FAIL")
        return 1
    for record in records:
        append_audit(record, args.output)
    print("audit_log: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
