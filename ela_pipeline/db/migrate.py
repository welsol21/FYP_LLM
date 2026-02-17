"""Apply PostgreSQL migrations for ELA persistence schema."""

from __future__ import annotations

import argparse
import os

from .repository import PostgresContractRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply PostgreSQL migrations for ELA DB schema.")
    parser.add_argument(
        "--db-url",
        default="",
        help="PostgreSQL DSN. If omitted, ELA_DATABASE_URL or DATABASE_URL env var is used.",
    )
    args = parser.parse_args()

    db_url = args.db_url or os.getenv("ELA_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise ValueError("PostgreSQL URL is required (pass --db-url or set ELA_DATABASE_URL/DATABASE_URL).")

    repo = PostgresContractRepository(db_url=db_url)
    repo.ensure_schema()
    print("Migrations applied successfully.")


if __name__ == "__main__":
    main()
