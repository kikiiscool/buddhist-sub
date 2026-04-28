"""Lightweight Celery app shared by backend (enqueue) & worker (consume).

The worker package owns task implementations; backend only signals task names.
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "buddhist_sub",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


# Task name constants (worker registers them under these names).
TASK_RUN_PIPELINE = "pipeline.run_job"
TASK_RUN_STEP = "pipeline.run_step"
