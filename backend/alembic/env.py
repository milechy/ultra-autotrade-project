# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Alembic migration environment configuration."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add backend directory to sys.path so app modules can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import all models so Alembic autogenerate can detect them
from app.ai.models import AIDecision  # noqa: F401, E402
from app.auth.models import User  # noqa: F401, E402
from app.database import Base, get_database_url  # noqa: E402
from app.fees.models import FeeConfigV10, FeeTransaction  # noqa: F401, E402
from app.knowledge.models import (  # noqa: F401, E402
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
)
from app.legal.models import TosConsent  # noqa: F401, E402
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot  # noqa: F401, E402
from app.proposals.models import Proposal  # noqa: F401, E402
from app.transactions.models import Transaction  # noqa: F401, E402
from app.users.models import UserSettings  # noqa: F401, E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use app's metadata for autogenerate support
target_metadata = Base.metadata


def get_url() -> str:
    """Return database URL from environment or alembic.ini."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    ini_url = config.get_main_option("sqlalchemy.url", "")
    if ini_url and ini_url != "driver://user:pass@localhost/dbname":
        return ini_url
    # Fallback to app's database URL resolver
    return get_database_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (direct DB connection)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
