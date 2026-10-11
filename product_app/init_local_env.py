"""Initialize private, per-install credentials for the local demo."""
from pathlib import Path

from auth import create_local_demo_env


def main() -> None:
    credentials = create_local_demo_env(Path(__file__).with_name(".env"))
    if credentials is None:
        print("Local .env already exists; leaving it unchanged.")
        return

    bank_password, customer_password = credentials
    print("Created a private localhost demo configuration.")
    print(f"Bank login: bank_manager / {bank_password}")
    print(f"Customer login: C12558 / {customer_password}")


if __name__ == "__main__":
    main()