"""Initialize private, per-install credentials for the local demo."""
import getpass
from pathlib import Path
import sys

from auth import hash_password, initialize_local_demo_env


def main() -> None:
    if sys.argv[1:] == ["--hash-password"]:
        password = getpass.getpass("Password to hash: ")
        if not password:
            raise SystemExit("Password must not be empty.")
        print(hash_password(password))
        return

    if sys.argv[1:]:
        raise SystemExit("Usage: init_local_env.py [--hash-password]")

    credentials = initialize_local_demo_env(Path(__file__).with_name(".env"))
    if credentials is None:
        return

    bank_password, customer_password = credentials
    print("Created or secured a private localhost demo configuration.")
    print(f"Bank login: bank_manager / {bank_password}")
    print(f"Customer login: C12558 / {customer_password}")


if __name__ == "__main__":
    main()