"""Small, dependency-free authentication boundary for the hackathon demo.

Credentials are loaded from environment variables (normally sourced from the
local, git-ignored .env file). This is deliberately a demo login, not a
replacement for a bank identity provider.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import tempfile


SCRYPT_N = 32_768
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 128 * 1024 * 1024
PASSWORD_HASH_PREFIX = f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"


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


def hash_password(password: str) -> str:
    """Return a salted scrypt verifier suitable for an environment variable."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
        dklen=32, maxmem=SCRYPT_MAXMEM,
    )
    return f"{PASSWORD_HASH_PREFIX}{salt.hex()}${digest.hex()}"


def _parse_password_hash(encoded: str) -> tuple[bytes, bytes] | None:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if (algorithm, int(n), int(r), int(p)) != ("scrypt", SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return None
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if len(salt) != 16 or len(digest) != 32:
            return None
        return salt, digest
    except ValueError:
        return None


def verify_password(password: str, encoded: str) -> bool:
    parsed = _parse_password_hash(encoded)
    if parsed is None:
        return False
    salt, expected = parsed
    actual = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
        dklen=32, maxmem=SCRYPT_MAXMEM,
    )
    return hmac.compare_digest(actual, expected)


def create_local_demo_env(path: Path) -> tuple[str, str] | None:
    """Create private, per-install demo credentials without overwriting config."""
    bank_password = secrets.token_urlsafe(32)
    customer_password = secrets.token_urlsafe(32)
    values = {
        "BANK_DEMO_ID": "bank_manager",
        "BANK_DEMO_PASSWORD_HASH": hash_password(bank_password),
        "CUSTOMER_DEMO_ID": "C12558",
        "CUSTOMER_DEMO_PASSWORD_HASH": hash_password(customer_password),
        "APP_SESSION_SECRET": secrets.token_urlsafe(48),
        "API_BASE_URL": "http://127.0.0.1:8000",
    }
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    with os.fdopen(descriptor, "w", encoding="utf-8") as env_file:
        env_file.write("".join(f"{key}={value}\n" for key, value in values.items()))
    return bank_password, customer_password


def migrate_local_demo_env(path: Path) -> tuple[str, str] | None:
    """Replace legacy local plaintext password entries with salted verifiers."""
    if not path.exists():
        return None

    lines = path.read_text(encoding="utf-8").splitlines()
    existing = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        existing.setdefault(key.strip(), value.strip().strip("'\""))

    legacy_keys = {
        "BANK_DEMO_PASSWORD": "BANK_DEMO_PASSWORD_HASH",
        "CUSTOMER_DEMO_PASSWORD": "CUSTOMER_DEMO_PASSWORD_HASH",
    }
    migrations = {
        new_key: (old_key, existing[old_key])
        for old_key, new_key in legacy_keys.items()
        if old_key in existing and new_key not in existing
    }
    changed = bool(migrations) or any(key in existing for key in legacy_keys)
    if not changed:
        return None

    output = []
    for raw_line in lines:
        line = raw_line.strip()
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key not in legacy_keys:
            output.append(raw_line)
    output.extend(f"{key}={hash_password(value)}" for key, (_, value) in migrations.items())

    descriptor, temporary_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as env_file:
            env_file.write("\n".join(output) + "\n")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    except Exception:
        os.unlink(temporary_path)
        raise

    bank_migration = migrations.get("BANK_DEMO_PASSWORD_HASH")
    customer_migration = migrations.get("CUSTOMER_DEMO_PASSWORD_HASH")
    if bank_migration and customer_migration:
        return bank_migration[1], customer_migration[1]
    return None


def initialize_local_demo_env(path: Path) -> tuple[str, str] | None:
    """Create a new local config or migrate its legacy plaintext passwords."""
    credentials = create_local_demo_env(path)
    return credentials if credentials is not None else migrate_local_demo_env(path)


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def authenticate(username: str, password: str) -> Principal | None:
    """Return the matching demo principal, or None for invalid credentials."""
    username = username.strip()
    bank_id = os.getenv("BANK_DEMO_ID", "")
    bank_password_hash = os.getenv("BANK_DEMO_PASSWORD_HASH", "")
    customer_id = os.getenv("CUSTOMER_DEMO_ID", "")
    customer_password_hash = os.getenv("CUSTOMER_DEMO_PASSWORD_HASH", "")

    if bank_id and _same(username, bank_id):
        if not verify_password(password, bank_password_hash):
            return None
        return Principal(username=bank_id, role="bank", display_name="Green Insights Manager")
    if customer_id and _same(username.upper(), customer_id.upper()):
        if not verify_password(password, customer_password_hash):
            return None
        return Principal(
            username=customer_id.upper(),
            role="customer",
            display_name=f"Customer {customer_id.upper()}",
            customer_id=customer_id.upper(),
        )
    return None


def credentials_ready() -> bool:
    required = ("BANK_DEMO_ID", "BANK_DEMO_PASSWORD_HASH", "CUSTOMER_DEMO_ID", "CUSTOMER_DEMO_PASSWORD_HASH")
    session_secret = os.getenv("APP_SESSION_SECRET", "")
    return (
        all(os.getenv(key) for key in required)
        and all(_parse_password_hash(os.getenv(key, "")) for key in ("BANK_DEMO_PASSWORD_HASH", "CUSTOMER_DEMO_PASSWORD_HASH"))
        and len(session_secret) >= 24
    )
