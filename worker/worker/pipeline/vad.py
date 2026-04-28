"""Voice activity detection — split audio into utterance windows.

Uses silero-vad via torch.hub. Returns list of (start_s, end_s) windows trimmed
to silence boundaries. Down-stream Whisper backends transcribe each window.

If silero is unavailable (no torch / no internet), falls back to fixed-length
30s windows so the pipeline still runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class Window:
    start_s: float
    end_s: float


def vad_split(audio_path: str, max_window_s: float = 30.0, min_window_s: float = 1.0) -> list[Window]:
    try:
        import torch
        import torchaudio
    except ImportError:
        return _fixed_windows(audio_path, max_window_s)

    try:
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        (get_speech_timestamps, _, read_audio, *_) = utils
    except Exception as e:
        logger.warning(f"silero-vad unavailable ({e}); falling back to fixed windows")
        return _fixed_windows(audio_path, max_window_s)

    sr = 16000
    wav = read_audio(audio_path, sampling_rate=sr)
    ts = get_speech_timestamps(wav, model, sampling_rate=sr, return_seconds=True)

    windows: list[Window] = []
    cur_start: float | None = None
    cur_end: float | None = None
    for seg in ts:
        s, e = float(seg["start"]), float(seg["end"])
        if cur_start is None:
            cur_start, cur_end = s, e
            continue
        # extend window if it would still fit
        if (e - cur_start) <= max_window_s and (s - cur_end) < 0.6:
            cur_end = e
        else:
            if cur_end - cur_start >= min_window_s:
                windows.append(Window(cur_start, cur_end))
            cur_start, cur_end = s, e
    if cur_start is not None and cur_end is not None and (cur_end - cur_start) >= min_window_s:
        windows.append(Window(cur_start, cur_end))

    if not windows:
        return _fixed_windows(audio_path, max_window_s)
    return windows


def _fixed_windows(audio_path: str, win: float) -> list[Window]:
    """Fallback: probe duration with soundfile and slice into fixed windows."""
    import soundfile as sf

    info = sf.info(audio_path)
    dur = info.frames / info.samplerate
    out: list[Window] = []
    t = 0.0
    while t < dur:
        out.append(Window(t, min(t + win, dur)))
        t += win
    return out
