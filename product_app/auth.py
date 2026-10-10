"""Small, dependency-free authentication boundary for the hackathon demo.

Credentials are loaded from environment variables (normally sourced from the
local, git-ignored .env file). This is deliberately a demo login, not a
replacement for a bank identity provider.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import os
from pathlib import Path


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    display_name: str
    customer_id: str | None = None


def load_local_env(path: Path) -> None:
    """Load KEY=VALUE pairs without overriding values already in the shell."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def authenticate(username: str, password: str) -> Principal | None:
    """Return the matching demo principal, or None for invalid credentials."""
    username, password = username.strip(), password.strip()
    bank_id = os.getenv("BANK_DEMO_ID", "")
    bank_password = os.getenv("BANK_DEMO_PASSWORD", "")
    customer_id = os.getenv("CUSTOMER_DEMO_ID", "")
    customer_password = os.getenv("CUSTOMER_DEMO_PASSWORD", "")

    if bank_id and bank_password and _same(username, bank_id) and _same(password, bank_password):
        return Principal(username=bank_id, role="bank", display_name="Green Insights Manager")
    if customer_id and customer_password and _same(username.upper(), customer_id.upper()) and _same(password, customer_password):
        return Principal(
            username=customer_id.upper(),
            role="customer",
            display_name=f"Customer {customer_id.upper()}",
            customer_id=customer_id.upper(),
        )
    return None


def credentials_ready() -> bool:
    required = ("BANK_DEMO_ID", "BANK_DEMO_PASSWORD", "CUSTOMER_DEMO_ID", "CUSTOMER_DEMO_PASSWORD")
    return all(os.getenv(key) for key in required)
