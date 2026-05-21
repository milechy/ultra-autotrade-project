#!/usr/bin/env python3
"""
DB migration gap detector.

Compares SQLAlchemy model definitions against the actual DB schema.
Outputs ALTER TABLE / CREATE TABLE statements for any detected gaps.

Exit codes:
  0 - no gaps
  1 - gaps found (run the suggested ALTER TABLE statements before deploying)
  2 - configuration / connection error
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect

from app.ai.models import AIDecision  # noqa: F401
from app.auth.models import User  # noqa: F401
from app.fees.models import FeeConfigV10, FeeTransaction  # noqa: F401
from app.database import Base, get_database_url
from app.invitations.models import Invitation  # noqa: F401
from app.knowledge.models import (  # noqa: F401
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
)
from app.notifications.models import NotificationLog  # noqa: F401
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot  # noqa: F401
from app.proposals.models import Proposal  # noqa: F401
from app.transactions.models import Transaction  # noqa: F401
from app.users.models import UserSettings  # noqa: F401


def _col_type_str(col: object) -> str:
    try:
        return str(col.type.compile(dialect=None))  # type: ignore[attr-defined]
    except Exception:
        return str(col.type)  # type: ignore[attr-defined]


def main() -> int:
    url = os.getenv("DATABASE_URL") or get_database_url()
    if "sqlite" in url.lower():
        print("[db-gap] SQLite detected -- skipping (PostgreSQL only)")
        return 0

    masked = url.split("@")[-1] if "@" in url else url
    print(f"[db-gap] Connecting to: ...@{masked}")

    try:
        engine = create_engine(url, connect_args={"connect_timeout": 10})
        inspector = sa_inspect(engine)
        db_table_names = set(inspector.get_table_names())
    except Exception as exc:
        print(f"DB connection failed: {exc}", file=sys.stderr)
        return 2

    has_gap = False

    for table_name, table in sorted(Base.metadata.tables.items()):
        if table_name == "alembic_version":
            continue

        if table_name not in db_table_names:
            has_gap = True
            col_defs = []
            for col in table.columns:
                nullable = "NULL" if col.nullable else "NOT NULL"
                col_defs.append(f"    {col.name} {_col_type_str(col)} {nullable}")
            print(f"\nMISSING TABLE: {table_name}")
            print(f"   --> CREATE TABLE {table_name} (")
            print(",\n".join(col_defs))
            print("   );")
            continue

        db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        model_cols = {c.name for c in table.columns}
        missing = sorted(model_cols - db_cols)

        for col_name in missing:
            has_gap = True
            col = table.c[col_name]
            nullable = "NULL" if col.nullable else "NOT NULL"
            default_clause = ""
            if col.default is not None:
                try:
                    arg = getattr(col.default, "arg", None)
                    if arg is not None and not callable(arg):
                        default_clause = f" DEFAULT '{arg}'"
                except Exception:  # noqa: S110
                    pass
            print(f"\nMISSING COLUMN: {table_name}.{col_name}")
            print(
                f"   --> ALTER TABLE {table_name} "
                f"ADD COLUMN IF NOT EXISTS {col_name} "
                f"{_col_type_str(col)} {nullable}{default_clause};"
            )

    if has_gap:
        print("\nSchema gaps detected -- run the ALTER TABLE statements above before deploying")
        return 1

    print("No schema gaps detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
