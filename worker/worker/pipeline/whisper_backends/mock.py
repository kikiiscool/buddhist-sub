"""Mock Whisper backend for CI / smoke tests.

Returns a fixed number of deterministic fake Cantonese segments so the rest of
the pipeline can be exercised end-to-end without installing a real ASR model
or hitting an external API. Activated via WHISPER_BACKEND=mock.

The "transcription" includes some intentional Whisper-style mishears (e.g.
「般弱波羅密」→ should be corrected to 「般若波羅蜜」 by dict_pass) so the
dictionary pre-pass is verifiable in the smoke test.
"""
from __future__ import annotations

from worker.pipeline.whisper_backends.base import TranscribedSegment, WhisperBackend


_FAKE_TEXTS = [
    "各位善男子善女人 今日我哋一齊嚟讀心經",  # clean — no errors expected
    "觀自在菩薩 行深般弱波羅密多時 照見五蘊皆空",  # 般弱→般若, 波羅密→波羅蜜
    "南無阿彌打佛 釋加牟尼佛 慈悲喜捨",  # 阿彌打→阿彌陀, 釋加→釋迦
]


class MockWhisperBackend(WhisperBackend):
    name = "mock"

    def transcribe(
        self,
        audio_path: str,
        language: str = "yue",
        initial_prompt: str | None = None,
        offset_s: float = 0.0,
    ) -> list[TranscribedSegment]:
        # Use the actual audio duration to allocate timestamps if available;
        # otherwise fall back to a fixed 3-second-per-segment layout.
        try:
            import soundfile as sf

            info = sf.info(audio_path)
            dur = max(0.1, info.frames / max(info.samplerate, 1))
        except Exception:
            dur = 9.0

        n = len(_FAKE_TEXTS)
        per = dur / n
        out: list[TranscribedSegment] = []
        for i, text in enumerate(_FAKE_TEXTS):
            start = offset_s + i * per
            end = offset_s + (i + 1) * per
            out.append(
                TranscribedSegment(
                    start_s=start,
                    end_s=end,
                    text=text,
                    confidence=-0.25,
                    words=[],
                )
            )
        return out
