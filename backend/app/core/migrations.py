"""Alembic migration runner — invoked from the FastAPI lifespan.

Runs in a worker thread (alembic itself is sync) so it doesn't block the
event loop. The alembic.ini at the backend root is the entry point;
DATABASE_URL is picked up by alembic/env.py from the environment.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # Ensure alembic resolves `script_location = alembic` against the
    # backend root regardless of where uvicorn is launched from.
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def upgrade_head_sync() -> None:
    cfg = _config()
    logger.info("alembic upgrade head — start")
    command.upgrade(cfg, "head")
    logger.info("alembic upgrade head — done")


async def upgrade_head() -> None:
    await asyncio.to_thread(upgrade_head_sync)
