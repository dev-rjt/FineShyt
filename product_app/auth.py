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
import secrets


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


def create_local_demo_env(path: Path) -> tuple[str, str] | None:
    """Create private, per-install demo credentials without overwriting config."""
    values = {
        "BANK_DEMO_ID": "bank_manager",
        "BANK_DEMO_PASSWORD": secrets.token_urlsafe(32),
        "CUSTOMER_DEMO_ID": "C12558",
        "CUSTOMER_DEMO_PASSWORD": secrets.token_urlsafe(32),
        "APP_SESSION_SECRET": secrets.token_urlsafe(48),
        "API_BASE_URL": "http://127.0.0.1:8000",
    }
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    with os.fdopen(descriptor, "w", encoding="utf-8") as env_file:
        env_file.write("".join(f"{key}={value}\n" for key, value in values.items()))
    return values["BANK_DEMO_PASSWORD"], values["CUSTOMER_DEMO_PASSWORD"]


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def authenticate(username: str, password: str) -> Principal | None:
    """Return the matching demo principal, or None for invalid credentials."""
    username = username.strip()
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
    session_secret = os.getenv("APP_SESSION_SECRET", "")
    return all(os.getenv(key) for key in required) and len(session_secret) >= 24
