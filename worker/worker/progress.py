"""Progress publisher: writes step state to DB and publishes events to Redis.

Frontend WebSocket subscribes to channel `job:{job_id}` and renders updates.
Worker also reads `job:{job_id}:control` for pause/resume signals.
"""
import json
import time
from datetime import datetime
from typing import Any

import redis

from worker.config import get_settings
from worker.db import Session, StepRun, StepStatus

_settings = get_settings()
_r = redis.Redis.from_url(_settings.redis_url, decode_responses=True)


def _channel(job_id: str) -> str:
    return f"job:{job_id}"


def publish(job_id: str, event: str, payload: dict[str, Any]) -> None:
    msg = json.dumps({"event": event, "ts": time.time(), **payload}, ensure_ascii=False)
    _r.publish(_channel(job_id), msg)


def step_started(job_id: str, step_name: str) -> None:
    with Session() as s:
        step = (
            s.query(StepRun)
            .filter(StepRun.job_id == job_id, StepRun.name == step_name)
            .one()
        )
        step.status = StepStatus.running
        step.progress = 0.0
        step.started_at = datetime.utcnow()
        s.commit()
    publish(job_id, "step.started", {"step": step_name})


def step_progress(job_id: str, step_name: str, progress: float, log: str | None = None) -> None:
    with Session() as s:
        step = (
            s.query(StepRun)
            .filter(StepRun.job_id == job_id, StepRun.name == step_name)
            .one()
        )
        step.progress = max(0.0, min(1.0, progress))
        if log:
            step.log = (step.log or "") + log + "\n"
        s.commit()
    publish(job_id, "step.progress", {"step": step_name, "progress": progress, "log": log})


def step_finished(
    job_id: str, step_name: str, metrics: dict | None = None, status: str = "completed"
) -> None:
    with Session() as s:
        step = (
            s.query(StepRun)
            .filter(StepRun.job_id == job_id, StepRun.name == step_name)
            .one()
        )
        step.status = StepStatus(status)
        step.progress = 1.0 if status == "completed" else step.progress
        step.finished_at = datetime.utcnow()
        if metrics:
            step.metrics = metrics
        s.commit()
    publish(job_id, "step.finished", {"step": step_name, "status": status, "metrics": metrics or {}})


def step_failed(job_id: str, step_name: str, error: str) -> None:
    with Session() as s:
        step = (
            s.query(StepRun)
            .filter(StepRun.job_id == job_id, StepRun.name == step_name)
            .one()
        )
        step.status = StepStatus.failed
        step.log = (step.log or "") + f"\nERROR: {error}"
        step.finished_at = datetime.utcnow()
        s.commit()
    publish(job_id, "step.failed", {"step": step_name, "error": error})


def is_paused_or_cancelled(job_id: str, step_name: str) -> tuple[bool, str | None]:
    """Worker calls this between chunks to honour pause/cancel."""
    with Session() as s:
        step = (
            s.query(StepRun)
            .filter(StepRun.job_id == job_id, StepRun.name == step_name)
            .one()
        )
        if step.status == StepStatus.paused:
            return True, "paused"
        if step.status == StepStatus.skipped:
            return True, "skipped"
    return False, None


def wait_while_paused(job_id: str, step_name: str, poll_s: float = 1.0) -> str | None:
    """Block until step leaves paused state. Returns 'cancelled' / 'skipped' / None."""
    while True:
        with Session() as s:
            step = (
                s.query(StepRun)
                .filter(StepRun.job_id == job_id, StepRun.name == step_name)
                .one()
            )
            if step.status == StepStatus.paused:
                pass  # keep waiting
            elif step.status == StepStatus.skipped:
                return "skipped"
            elif step.status == StepStatus.running:
                return None
            else:
                return step.status.value
        time.sleep(poll_s)
