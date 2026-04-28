"""Celery tasks: pipeline orchestration.

run_job: drives the whole pipeline step-by-step, honouring pause/skip/cancel.
run_step: re-runs a single step (used when the user clicks "Retry").
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from loguru import logger
from sqlalchemy import select

from worker.celery_app import celery_app
from worker.config import get_settings
from worker.db import Job, JobStatus, Segment, Session, StepName, StepRun, StepStatus
from worker.pipeline.correct import correct_segment
from worker.pipeline.dict_pass import apply_dict
from worker.pipeline.rag import search as rag_search
from worker.pipeline.srt import build_srt
from worker.pipeline.vad import vad_split
from worker.pipeline.whisper_backends import get_backend
from worker.progress import (
    publish,
    step_failed,
    step_finished,
    step_progress,
    step_started,
    wait_while_paused,
)
from worker.storage import download_to_tmp, upload_file

_settings = get_settings()


# -------- step implementations --------------------------------------------------


def _do_vad(job_id: str, audio_path: str) -> list[dict]:
    step_started(job_id, StepName.vad.value)
    windows = vad_split(audio_path)
    step_progress(job_id, StepName.vad.value, 1.0, f"{len(windows)} windows")
    step_finished(job_id, StepName.vad.value, metrics={"windows": len(windows)})
    return [{"start_s": w.start_s, "end_s": w.end_s} for w in windows]


def _do_transcribe(job_id: str, audio_path: str, windows: list[dict]) -> None:
    step_started(job_id, StepName.transcribe.value)
    backend = get_backend()
    initial_prompt = _settings.whisper_initial_prompt or None

    n = len(windows)
    seg_idx = 0
    with Session() as s:
        # wipe old segments if re-running
        s.query(Segment).filter(Segment.job_id == job_id).delete()
        s.commit()

    for wi, w in enumerate(windows):
        if wait_while_paused(job_id, StepName.transcribe.value) == "skipped":
            break
        # NOTE: feed the FULL audio with offset; mlx/faster handle slicing
        # internally via `clip_timestamps` or we trim the file. For simplicity
        # we trim to a tmp file per window.
        tmp_clip = _trim(audio_path, w["start_s"], w["end_s"])
        try:
            tsegs = backend.transcribe(
                tmp_clip,
                language=_settings.whisper_language,
                initial_prompt=initial_prompt,
                offset_s=w["start_s"],
            )
        finally:
            try:
                os.remove(tmp_clip)
            except OSError:
                pass

        with Session() as s:
            for ts in tsegs:
                s.add(
                    Segment(
                        id=uuid.uuid4(),
                        job_id=uuid.UUID(job_id),
                        idx=seg_idx,
                        start_s=ts.start_s,
                        end_s=ts.end_s,
                        text_raw=ts.text,
                        confidence=ts.confidence,
                    )
                )
                seg_idx += 1
            s.commit()

        publish(job_id, "segments.appended", {"count": len(tsegs), "total": seg_idx})
        step_progress(job_id, StepName.transcribe.value, (wi + 1) / max(n, 1))

    step_finished(job_id, StepName.transcribe.value, metrics={"segments": seg_idx})


def _do_dict_pass(job_id: str) -> None:
    step_started(job_id, StepName.dict_pass.value)
    with Session() as s:
        segs = list(s.query(Segment).filter(Segment.job_id == job_id).order_by(Segment.idx))
        n = len(segs) or 1
        for i, seg in enumerate(segs):
            corrected, _log = apply_dict(seg.text_raw)
            seg.text_dict = corrected
            if (i + 1) % 25 == 0:
                s.commit()
                step_progress(job_id, StepName.dict_pass.value, (i + 1) / n)
        s.commit()
    step_finished(job_id, StepName.dict_pass.value)


def _do_rag_correct(job_id: str) -> None:
    step_started(job_id, StepName.rag_correct.value)
    with Session() as s:
        segs = list(s.query(Segment).filter(Segment.job_id == job_id).order_by(Segment.idx))
    n = len(segs) or 1
    for i, seg in enumerate(segs):
        if wait_while_paused(job_id, StepName.rag_correct.value) == "skipped":
            break
        prev_ctx = segs[i - 1].text_dict or segs[i - 1].text_raw if i > 0 else ""
        next_ctx = segs[i + 1].text_dict or segs[i + 1].text_raw if i + 1 < len(segs) else ""
        raw = seg.text_dict or seg.text_raw
        try:
            hits = rag_search(raw, top_k=4)
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")
            hits = []

        try:
            res = correct_segment(raw, prev_ctx, next_ctx, hits)
            ai_text = res.text
            notes = res.notes
        except Exception as e:
            logger.exception("Qwen call failed; falling back to dict text")
            ai_text = raw
            notes = f"qwen error: {e}"

        with Session() as s2:
            db_seg = s2.get(Segment, seg.id)
            db_seg.text_ai = ai_text
            db_seg.text_final = ai_text  # default; user can override
            db_seg.rag_refs = [
                {"canon": h.canon, "work_id": h.work_id, "juan": h.juan, "score": h.score}
                for h in hits
            ]
            s2.commit()

        publish(
            job_id,
            "segment.corrected",
            {"idx": seg.idx, "text": ai_text, "notes": notes, "rag_count": len(hits)},
        )
        step_progress(job_id, StepName.rag_correct.value, (i + 1) / n)

    step_finished(job_id, StepName.rag_correct.value)


def _do_review(job_id: str) -> None:
    """Pause for human review. UI calls /steps/review/action with action=resume."""
    step_started(job_id, StepName.review.value)
    publish(job_id, "review.requested", {})
    with Session() as s:
        step = (
            s.query(StepRun)
            .filter(StepRun.job_id == job_id, StepRun.name == StepName.review.value)
            .one()
        )
        step.status = StepStatus.paused
        s.commit()
    state = wait_while_paused(job_id, StepName.review.value)
    step_finished(job_id, StepName.review.value, status="completed" if state != "skipped" else "skipped")


def _do_srt(job_id: str) -> None:
    step_started(job_id, StepName.srt.value)
    with Session() as s:
        segs = list(s.query(Segment).filter(Segment.job_id == job_id).order_by(Segment.idx))
        rows = [
            {
                "idx": x.idx,
                "start_s": x.start_s,
                "end_s": x.end_s,
                "text_final": x.text_final,
                "text_ai": x.text_ai,
                "text_dict": x.text_dict,
                "text_raw": x.text_raw,
            }
            for x in segs
        ]
    srt_text = build_srt(rows)
    out_key = f"output/{job_id}/subtitles.srt"
    tmp_path = f"/tmp/{job_id}.srt"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(srt_text)
    upload_file(tmp_path, out_key, content_type="application/x-subrip")
    publish(job_id, "srt.ready", {"key": out_key, "bytes": len(srt_text.encode("utf-8"))})
    step_finished(job_id, StepName.srt.value, metrics={"key": out_key})


# -------- helpers --------------------------------------------------------------


def _trim(audio_path: str, start_s: float, end_s: float) -> str:
    """Cut a clip [start_s, end_s] from the audio to a tmp wav file."""
    import tempfile

    from pydub import AudioSegment

    audio = AudioSegment.from_file(audio_path)
    clip = audio[int(start_s * 1000) : int(end_s * 1000)]
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    out.close()
    clip.set_frame_rate(16000).set_channels(1).export(out.name, format="wav")
    return out.name


def _set_job_status(job_id: str, status: JobStatus, error: str | None = None) -> None:
    with Session() as s:
        j = s.get(Job, uuid.UUID(job_id))
        j.status = status
        if error:
            j.error = error
        j.updated_at = datetime.utcnow()
        s.commit()


# -------- celery entry points --------------------------------------------------


@celery_app.task(name="pipeline.run_job", bind=True, max_retries=0)
def run_job(self, job_id: str) -> None:
    logger.info(f"run_job {job_id}")
    _set_job_status(job_id, JobStatus.running)
    publish(job_id, "job.started", {})

    audio_path = None
    try:
        with Session() as s:
            job = s.get(Job, uuid.UUID(job_id))
            audio_key = job.audio_key

        audio_path = download_to_tmp(audio_key, suffix=".mp3")

        # 1. VAD
        windows = _do_vad(job_id, audio_path)
        # 2. Transcribe
        _do_transcribe(job_id, audio_path, windows)
        # 3. Dictionary pre-pass
        _do_dict_pass(job_id)
        # 4. RAG + Qwen correction
        _do_rag_correct(job_id)
        # 5. Human review (pauses)
        _do_review(job_id)
        # 6. Build SRT
        _do_srt(job_id)

        _set_job_status(job_id, JobStatus.completed)
        publish(job_id, "job.completed", {})
    except Exception as e:
        logger.exception("pipeline failed")
        _set_job_status(job_id, JobStatus.failed, error=str(e))
        publish(job_id, "job.failed", {"error": str(e)})
    finally:
        if audio_path:
            try:
                os.remove(audio_path)
            except OSError:
                pass


@celery_app.task(name="pipeline.run_step", bind=True, max_retries=0)
def run_step(self, job_id: str, step_name: str) -> None:
    """Re-run a single step (used by the Retry button)."""
    logger.info(f"run_step {job_id} {step_name}")
    audio_path = None
    try:
        if step_name in (StepName.vad.value, StepName.transcribe.value):
            with Session() as s:
                job = s.get(Job, uuid.UUID(job_id))
                audio_key = job.audio_key
            audio_path = download_to_tmp(audio_key, suffix=".mp3")

        if step_name == StepName.vad.value:
            _do_vad(job_id, audio_path)
        elif step_name == StepName.transcribe.value:
            with Session() as s:
                # reuse VAD result if exists
                step = (
                    s.query(StepRun)
                    .filter(StepRun.job_id == job_id, StepRun.name == StepName.vad.value)
                    .one()
                )
                windows = step.metrics.get("windows_list") or []
            if not windows:
                windows = _do_vad(job_id, audio_path)
            _do_transcribe(job_id, audio_path, windows)
        elif step_name == StepName.dict_pass.value:
            _do_dict_pass(job_id)
        elif step_name == StepName.rag_correct.value:
            _do_rag_correct(job_id)
        elif step_name == StepName.review.value:
            _do_review(job_id)
        elif step_name == StepName.srt.value:
            _do_srt(job_id)
        else:
            raise ValueError(f"unknown step {step_name}")
    except Exception as e:
        step_failed(job_id, step_name, str(e))
    finally:
        if audio_path:
            try:
                os.remove(audio_path)
            except OSError:
                pass
