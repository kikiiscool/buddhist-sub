from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import jobs, upload, ws
from app.core.config import get_settings
from app.core.migrations import upgrade_head

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """DB initialisation policy:

    * SKIP_DB_INIT=1 — touch nothing. Used when smoke-testing the import
      path or when the deployment runs migrations entirely externally and
      doesn't even want logs from this code path.
    * RUN_MIGRATIONS_ON_START=1 (default) — run `alembic upgrade head`.
      Convenient for dev (`uvicorn ... --reload`) and acceptable for
      single-replica deployments.
    * RUN_MIGRATIONS_ON_START=0 — assume migrations were applied by an
      init container / CI job before the app started. Recommended for
      multi-replica production to avoid migration races between replicas.
    """
    if settings.skip_db_init:
        logger.warning("Skipping DB init (SKIP_DB_INIT=1)")
    elif settings.run_migrations_on_start:
        await upgrade_head()
    else:
        logger.info(
            "RUN_MIGRATIONS_ON_START=0 — expecting migrations to be applied externally"
        )
    logger.info("Buddhist subtitle backend started")
    yield


app = FastAPI(title="Buddhist Dharma Subtitle Generator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(ws.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}
