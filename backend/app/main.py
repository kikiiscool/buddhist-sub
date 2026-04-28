from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import jobs, upload, ws
from app.core.config import get_settings
from app.core.db import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Dev-mode auto-create. Prod uses alembic migrations.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
