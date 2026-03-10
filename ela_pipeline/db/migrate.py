"""Apply DB schema migrations for ELA persistence schema."""

from __future__ import annotations

import argparse
import os

from .repository import build_contract_repository, resolve_db_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply DB schema migrations for ELA persistence.")
    parser.add_argument(
        "--db-url",
        default="",
        help="DB URL/path override. For postgres use DSN, for sqlite use file path or sqlite:///path.",
    )
    parser.add_argument(
        "--db-backend",
        default="",
        choices=["", "sqlite", "postgres"],
        help="Backend override. If omitted, ELA_DB_BACKEND is used (default: sqlite).",
    )
    args = parser.parse_args()
    backend = args.db_backend or os.getenv("ELA_DB_BACKEND", "").strip() or "sqlite"
    db_url = args.db_url
    if backend == "postgres":
        db_url = db_url or os.getenv("ELA_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
        if not db_url:
            raise ValueError("PostgreSQL URL is required (pass --db-url or set ELA_DATABASE_URL/DATABASE_URL).")

    repo = build_contract_repository(db_url=db_url, backend=backend)
    repo.ensure_schema()
    print(f"Migrations applied successfully ({resolve_db_backend(backend, db_url)}).")


if __name__ == "__main__":
    main()
