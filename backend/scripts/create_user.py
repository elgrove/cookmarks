"""Seed an account from the command line — how the first admin is created.

    uv run python -m scripts.create_user aaron --admin

In production: `docker compose exec cookmarks python -m scripts.create_user <name> --admin`
from the backend directory. The first account created adopts every pre-accounts list, so
an existing deployment keeps its Favourites.
"""

import argparse
import sys
from getpass import getpass

from app.db import SessionLocal
from app.services.users import UserError, create_user


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Cookmarks account.")
    parser.add_argument("username")
    parser.add_argument("--admin", action="store_true", help="grant admin rights")
    args = parser.parse_args()

    password = getpass("Password: ")
    if password != getpass("Repeat password: "):
        print("passwords do not match", file=sys.stderr)
        return 1

    with SessionLocal() as session:
        try:
            user = create_user(session, args.username, password, args.admin)
        except UserError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(f"created {user.username}{' (admin)' if user.is_admin else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
