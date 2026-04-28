from celery import Celery

from worker.config import get_settings

settings = get_settings()

celery_app = Celery(
    "buddhist_sub",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # one heavy step at a time per worker process
    worker_concurrency=1,
)
