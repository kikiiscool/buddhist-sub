"""faster-whisper backend (CTranslate2). For production k8s GPU nodes or CPU fallback."""
from __future__ import annotations

import os
from worker.config import get_settings
from worker.pipeline.whisper_backends.base import TranscribedSegment, WhisperBackend


class FasterWhisperBackend(WhisperBackend):
    name = "faster"

    def __init__(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise RuntimeError("faster-whisper not installed. pip install faster-whisper") from e

        s = get_settings()
        device = os.getenv("WHISPER_DEVICE", "auto")  # auto | cpu | cuda
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "auto")
        self.model = WhisperModel(s.whisper_model, device=device, compute_type=compute_type)

    def transcribe(
        self,
        audio_path: str,
        language: str = "yue",
        initial_prompt: str | None = None,
        offset_s: float = 0.0,
    ) -> list[TranscribedSegment]:
        segments, _info = self.model.transcribe(
            audio_path,
            language=language,
            initial_prompt=initial_prompt or None,
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=False,  # we already VAD-split upstream
            temperature=0.0,
        )
        out: list[TranscribedSegment] = []
        for seg in segments:
            out.append(
                TranscribedSegment(
                    start_s=float(seg.start) + offset_s,
                    end_s=float(seg.end) + offset_s,
                    text=(seg.text or "").strip(),
                    confidence=getattr(seg, "avg_logprob", None),
                    words=[
                        {"w": w.word.strip(), "start": w.start + offset_s, "end": w.end + offset_s, "prob": w.probability}
                        for w in (seg.words or [])
                    ],
                )
            )
        return out
