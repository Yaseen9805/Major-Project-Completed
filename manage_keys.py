"""CLI for issuing API keys (Module 6).

Run: python manage_keys.py create <owner_name>
"""

import sys

import db


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "create":
        print("Usage: python manage_keys.py create <owner_name>")
        raise SystemExit(1)

    owner = sys.argv[2]
    key = db.create_api_key(owner)
    print(f"Created API key for '{owner}': {key}")


if __name__ == "__main__":
    main()
