import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    audio_key: Mapped[str] = mapped_column(String(512))
    audio_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"),
        default=JobStatus.pending,
    )
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    steps: Mapped[list["StepRun"]] = relationship(
        back_populates="job",
        order_by="StepRun.order_idx",
        cascade="all, delete-orphan",
    )
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="job",
        order_by="Segment.idx",
        cascade="all, delete-orphan",
    )


class StepRun(Base):
    __tablename__ = "step_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
    )
    name: Mapped[StepName] = mapped_column(Enum(StepName, name="step_name"))
    order_idx: Mapped[int] = mapped_column(Integer)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, name="step_status"),
        default=StepStatus.pending,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)

    job: Mapped[Job] = relationship(back_populates="steps")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
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
