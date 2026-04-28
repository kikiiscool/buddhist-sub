from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranscribedSegment:
    start_s: float
    end_s: float
    text: str
    confidence: float | None = None
    words: list[dict] = field(default_factory=list)  # [{w, start, end, prob}]


class WhisperBackend(ABC):
    name: str = "base"

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str = "yue",
        initial_prompt: str | None = None,
        offset_s: float = 0.0,
    ) -> list[TranscribedSegment]:
        """Transcribe an audio file. ``offset_s`` is added to all timestamps so
        results from windowed audio align with the source timeline."""
