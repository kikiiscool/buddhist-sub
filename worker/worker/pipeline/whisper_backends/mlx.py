"""Apple MLX Whisper backend — optimal for Apple M-series (M1/M2/M3/M4).

Install on macOS:  pip install mlx-whisper
Models auto-download to ~/.cache/huggingface — use mlx-community/whisper-large-v3-mlx
"""
from __future__ import annotations

from worker.config import get_settings
from worker.pipeline.whisper_backends.base import TranscribedSegment, WhisperBackend


class MlxWhisperBackend(WhisperBackend):
    name = "mlx"

    def __init__(self):
        try:
            import mlx_whisper  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "mlx-whisper not installed. Run: pip install mlx-whisper "
                "(macOS Apple Silicon only)"
            ) from e
        self._model_repo = self._resolve_repo(get_settings().whisper_model)

    @staticmethod
    def _resolve_repo(model: str) -> str:
        # Map common short names to mlx-community Hub repos.
        mapping = {
            "large-v3": "mlx-community/whisper-large-v3-mlx",
            "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
            "medium": "mlx-community/whisper-medium-mlx",
            "small": "mlx-community/whisper-small-mlx",
        }
        return mapping.get(model, model)

    def transcribe(
        self,
        audio_path: str,
        language: str = "yue",
        initial_prompt: str | None = None,
        offset_s: float = 0.0,
    ) -> list[TranscribedSegment]:
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=self._model_repo,
            language=language,
            initial_prompt=initial_prompt or None,
            word_timestamps=True,
            condition_on_previous_text=False,  # avoid hallucination loops
            temperature=0.0,
        )
        out: list[TranscribedSegment] = []
        for seg in result.get("segments", []):
            out.append(
                TranscribedSegment(
                    start_s=float(seg["start"]) + offset_s,
                    end_s=float(seg["end"]) + offset_s,
                    text=seg["text"].strip(),
                    confidence=seg.get("avg_logprob"),
                    words=[
                        {
                            "w": w.get("word", "").strip(),
                            "start": float(w["start"]) + offset_s,
                            "end": float(w["end"]) + offset_s,
                            "prob": w.get("probability"),
                        }
                        for w in seg.get("words", [])
                    ],
                )
            )
        return out
