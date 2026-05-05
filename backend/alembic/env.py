"""Alembic migration environment.

Reads DATABASE_URL from env. Strips the asyncpg driver suffix and uses the
sync psycopg2 driver for migrations — keeps env.py simple (sync), and the
runtime app still uses asyncpg for serving requests.
"""
from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable regardless of where alembic is invoked from.
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import Base  # noqa: E402
import app.models  # noqa: E402,F401  — register models with Base.metadata


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    raw = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or ""
    if not raw:
        raise RuntimeError(
            "DATABASE_URL must be set for alembic migrations "
            "(or sqlalchemy.url in alembic.ini)"
        )
    # Migrations run sync — swap asyncpg → psycopg2.
    return raw.replace("+asyncpg", "+psycopg2")


URL = _resolve_url()
config.set_main_option("sqlalchemy.url", URL)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """Don't let autogenerate touch tables that aren't owned by SQLAlchemy
    models. `cbeta_chunks` is created by scripts/ingest_cbeta.py and uses
    pgvector types alembic doesn't understand — leave it alone."""
    if type_ == "table" and name == "cbeta_chunks":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = URL
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
