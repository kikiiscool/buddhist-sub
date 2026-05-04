from worker.config import get_settings
from worker.pipeline.whisper_backends.base import TranscribedSegment, WhisperBackend


def get_backend() -> WhisperBackend:
    name = get_settings().whisper_backend
    if name == "mlx":
        from worker.pipeline.whisper_backends.mlx import MlxWhisperBackend
        return MlxWhisperBackend()
    if name == "faster":
        from worker.pipeline.whisper_backends.faster import FasterWhisperBackend
        return FasterWhisperBackend()
    if name == "openai":
        from worker.pipeline.whisper_backends.openai_api import OpenAIWhisperBackend
        return OpenAIWhisperBackend()
    if name == "mock":
        from worker.pipeline.whisper_backends.mock import MockWhisperBackend
        return MockWhisperBackend()
    raise ValueError(f"unknown WHISPER_BACKEND={name}")


__all__ = ["get_backend", "WhisperBackend", "TranscribedSegment"]
