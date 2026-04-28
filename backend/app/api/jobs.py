import uuid
from datetime import timedelta

import srt as srtlib
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.job import Job, JobStatus, Segment, StepName, StepRun, StepStatus
from app.schemas.job import (
    JobCreate,
    JobOut,
    SegmentOut,
    SegmentUpdate,
    StepActionIn,
)
from app.tasks.celery_app import TASK_RUN_PIPELINE, TASK_RUN_STEP, celery_app

router = APIRouter(prefix="/jobs", tags=["jobs"])


PIPELINE_STEPS: list[StepName] = [
    StepName.vad,
    StepName.transcribe,
    StepName.dict_pass,
    StepName.rag_correct,
    StepName.review,
    StepName.srt,
]


@router.post("", response_model=JobOut)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db)) -> JobOut:
    job = Job(name=payload.name, audio_key=payload.audio_key, config=payload.config)
    db.add(job)
    await db.flush()
    for i, step in enumerate(PIPELINE_STEPS):
        db.add(StepRun(job_id=job.id, name=step, order_idx=i))
    await db.commit()
    await db.refresh(job, attribute_names=["steps"])

    celery_app.send_task(TASK_RUN_PIPELINE, args=[str(job.id)])
    return JobOut.model_validate(job)


@router.get("", response_model=list[JobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[JobOut]:
    res = await db.execute(select(Job).order_by(Job.created_at.desc()))
    jobs = res.scalars().all()
    out: list[JobOut] = []
    for j in jobs:
        await db.refresh(j, attribute_names=["steps"])
        out.append(JobOut.model_validate(j))
    return out


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> JobOut:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    await db.refresh(job, attribute_names=["steps"])
    return JobOut.model_validate(job)


@router.get("/{job_id}/segments", response_model=list[SegmentOut])
async def get_segments(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[SegmentOut]:
    res = await db.execute(
        select(Segment).where(Segment.job_id == job_id).order_by(Segment.idx)
    )
    return [SegmentOut.model_validate(s) for s in res.scalars().all()]


@router.patch("/{job_id}/segments/{segment_id}", response_model=SegmentOut)
async def update_segment(
    job_id: uuid.UUID,
    segment_id: uuid.UUID,
    payload: SegmentUpdate,
    db: AsyncSession = Depends(get_db),
) -> SegmentOut:
    seg = await db.get(Segment, segment_id)
    if not seg or seg.job_id != job_id:
        raise HTTPException(404)
    seg.text_final = payload.text_final
    seg.edited_by_human = True
    await db.commit()
    await db.refresh(seg)
    return SegmentOut.model_validate(seg)


@router.post("/{job_id}/steps/{step_name}/action")
async def step_action(
    job_id: uuid.UUID,
    step_name: StepName,
    payload: StepActionIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """pause / resume / retry / skip a step. The worker checks the step status
    before each chunk and reacts. Retry re-enqueues the step task."""
    res = await db.execute(
        select(StepRun).where(StepRun.job_id == job_id, StepRun.name == step_name)
    )
    step = res.scalar_one_or_none()
    if not step:
        raise HTTPException(404)

    action = payload.action
    if action == "pause":
        step.status = StepStatus.paused
    elif action == "resume":
        step.status = StepStatus.running
    elif action == "skip":
        step.status = StepStatus.skipped
        step.progress = 1.0
    elif action == "retry":
        step.status = StepStatus.pending
        step.progress = 0.0
        step.log = None
        celery_app.send_task(TASK_RUN_STEP, args=[str(job_id), step_name.value])
    else:
        raise HTTPException(400, f"unknown action {action}")

    await db.commit()
    return {"ok": True, "status": step.status.value}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404)
    job.status = JobStatus.cancelled
    await db.commit()
    return {"ok": True}


@router.get("/{job_id}/srt", response_class=PlainTextResponse)
async def download_srt(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    res = await db.execute(
        select(Segment).where(Segment.job_id == job_id).order_by(Segment.idx)
    )
    segs = res.scalars().all()
    subs = []
    for i, seg in enumerate(segs, start=1):
        text = seg.text_final or seg.text_ai or seg.text_dict or seg.text_raw or ""
        if not text.strip():
            continue
        subs.append(
            srtlib.Subtitle(
                index=i,
                start=timedelta(seconds=float(seg.start_s)),
                end=timedelta(seconds=float(seg.end_s)),
                content=text.strip(),
            )
        )
    body = srtlib.compose(subs)
    return PlainTextResponse(
        body,
        media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{job_id}.srt"'},
    )
