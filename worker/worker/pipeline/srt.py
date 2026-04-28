"""Assemble final SRT from segments."""
from __future__ import annotations

from datetime import timedelta

import srt as srtlib


def build_srt(segments: list[dict]) -> str:
    """segments: list of {idx, start_s, end_s, text_final}"""
    subs = []
    for i, seg in enumerate(segments, start=1):
        text = seg.get("text_final") or seg.get("text_ai") or seg.get("text_dict") or seg.get("text_raw") or ""
        if not text.strip():
            continue
        subs.append(
            srtlib.Subtitle(
                index=i,
                start=timedelta(seconds=float(seg["start_s"])),
                end=timedelta(seconds=float(seg["end_s"])),
                content=text.strip(),
            )
        )
    return srtlib.compose(subs)
