"""initial schema: jobs / step_runs / segments

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-04

Hand-authored baseline migration that matches the SQLAlchemy models in
backend/app/models/job.py at the time this PR landed. Future schema
changes should be added as new revision files (autogenerate is fine, but
review the diff carefully — especially around enum types).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Postgres enum value lists (must match StrEnum members in models/job.py).
JOB_STATUSES = ("pending", "running", "paused", "completed", "failed", "cancelled")
STEP_NAMES = ("upload", "vad", "transcribe", "dict_pass", "rag_correct", "review", "srt")
STEP_STATUSES = ("pending", "running", "paused", "completed", "failed", "skipped")


def upgrade() -> None:
    # Postgres extensions used by the platform. CREATE EXTENSION needs
    # superuser-ish rights — managed Postgres providers usually allow these
    # two; surface a clear error early if not.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    job_status = postgresql.ENUM(*JOB_STATUSES, name="job_status", create_type=False)
    step_name = postgresql.ENUM(*STEP_NAMES, name="step_name", create_type=False)
    step_status = postgresql.ENUM(*STEP_STATUSES, name="step_status", create_type=False)

    # Create types explicitly so we control the order independently of
    # create_table inferring them.
    job_status.create(op.get_bind(), checkfirst=True)
    step_name.create(op.get_bind(), checkfirst=True)
    step_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("audio_key", sa.String(length=512), nullable=False),
        sa.Column("audio_duration_s", sa.Float(), nullable=True),
        sa.Column("status", job_status, nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "step_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", step_name, nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("status", step_status, nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
    )
    op.create_index("ix_step_runs_job_id", "step_runs", ["job_id"])

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("text_raw", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_dict", sa.Text(), nullable=True),
        sa.Column("text_ai", sa.Text(), nullable=True),
        sa.Column("text_final", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rag_refs", sa.JSON(), nullable=False),
        sa.Column(
            "edited_by_human",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_segments_job_id", "segments", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_segments_job_id", table_name="segments")
    op.drop_table("segments")
    op.drop_index("ix_step_runs_job_id", table_name="step_runs")
    op.drop_table("step_runs")
    op.drop_table("jobs")

    bind = op.get_bind()
    postgresql.ENUM(name="step_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="step_name").drop(bind, checkfirst=True)
    postgresql.ENUM(name="job_status").drop(bind, checkfirst=True)
    # NOTE: we deliberately do NOT drop the vector / pg_trgm extensions
    # here — other tables (e.g. cbeta_chunks) may still depend on them,
    # and extensions are a shared cluster resource.
