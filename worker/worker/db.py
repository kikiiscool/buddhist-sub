"""Synchronous SQLAlchemy session for Celery tasks (Celery is sync).

We re-declare lightweight ORM models matching backend/app/models/job.py so the
worker doesn't have to import the backend package. Keep the schema in sync.
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from worker.config import get_settings


class Base(DeclarativeBase):
    pass


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class StepName(StrEnum):
    upload = "upload"
    vad = "vad"
    transcribe = "transcribe"
    dict_pass = "dict_pass"
    rag_correct = "rag_correct"
    review = "review"
    srt = "srt"


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    audio_key: Mapped[str] = mapped_column(String(512))
    audio_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"))
    config: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    steps: Mapped[list["StepRun"]] = relationship(
        back_populates="job", order_by="StepRun.order_idx"
    )
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="job", order_by="Segment.idx"
    )


class StepRun(Base):
    __tablename__ = "step_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    name: Mapped[StepName] = mapped_column(Enum(StepName, name="step_name"))
    order_idx: Mapped[int] = mapped_column(Integer)
    status: Mapped[StepStatus] = mapped_column(Enum(StepStatus, name="step_status"))
    progress: Mapped[float] = mapped_column(Float)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON)
    job: Mapped[Job] = relationship(back_populates="steps")


class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    idx: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    text_raw: Mapped[str] = mapped_column(Text, default="")
    text_dict: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_ai: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rag_refs: Mapped[list] = mapped_column(JSON, default=list)
    edited_by_human: Mapped[bool] = mapped_column(default=False)
    job: Mapped[Job] = relationship(back_populates="segments")


_settings = get_settings()
# worker uses sync URL — strip asyncpg driver if present
_sync_url = _settings.database_url.replace("+asyncpg", "")
engine = create_engine(_sync_url, pool_pre_ping=True, future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
