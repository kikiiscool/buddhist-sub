"""OpenAI Whisper API backend (cloud fallback). No GPU needed."""
from __future__ import annotations

from worker.config import get_settings
from worker.pipeline.whisper_backends.base import TranscribedSegment, WhisperBackend


class OpenAIWhisperBackend(WhisperBackend):
    name = "openai"

    def __init__(self):
        from openai import OpenAI

        s = get_settings()
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=s.openai_api_key)

    def transcribe(
        self,
        audio_path: str,
        language: str = "yue",
        initial_prompt: str | None = None,
        offset_s: float = 0.0,
    ) -> list[TranscribedSegment]:
        with open(audio_path, "rb") as f:
            resp = self.client.audio.transcriptions.create(
                file=f,
                model="whisper-1",
                language=language if language != "yue" else "zh",  # API has no yue
                prompt=initial_prompt or "",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        out: list[TranscribedSegment] = []
        for seg in resp.segments or []:
            out.append(
                TranscribedSegment(
                    start_s=float(seg.start) + offset_s,
                    end_s=float(seg.end) + offset_s,
                    text=seg.text.strip(),
                    confidence=getattr(seg, "avg_logprob", None),
                )
            )
        return out
