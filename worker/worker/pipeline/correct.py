"""Qwen-based subtitle correction.

For each segment we feed:
  - 前一句 (context before)
  - 本句 (raw + dict-pass version)
  - 後一句 (context after)
  - 檢索到嘅 CBETA 經文段落 (RAG hits)

Qwen returns ONLY the corrected text for the current segment. We use JSON mode
so the output is parseable.

Prompt-caching note: DashScope supports system-prompt caching when the same
system prompt is reused across requests within a session. We keep the system
prompt static and put dynamic context in the user message.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from worker.config import get_settings
from worker.pipeline.rag import CbetaHit

_settings = get_settings()


def _is_mock() -> bool:
    return os.environ.get("MOCK_AI", "").lower() in ("1", "true", "yes")


def _client() -> OpenAI:
    return OpenAI(api_key=_settings.dashscope_api_key, base_url=_settings.dashscope_base_url)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[3] / "data" / "prompts" / "qwen_correct.md"


def _system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    # minimal fallback
    return (
        "你係粵語佛法字幕校對員。輸入係 Whisper 自動轉錄嘅粵語講座字幕,"
        "可能有同音錯字、佛教專名錯字。請參考提供嘅 CBETA 經文做校正,"
        "輸出 JSON: {\"text\": \"校正後字幕\", \"changed\": true/false, \"notes\": \"...\"}。"
        "保留口語、保留粵語用字,只改錯字,唔好改寫意思。"
    )


@dataclass
class CorrectionResult:
    text: str
    changed: bool
    notes: str
    model: str


def correct_segment(
    raw: str,
    prev_ctx: str,
    next_ctx: str,
    rag_hits: list[CbetaHit],
    model: str | None = None,
) -> CorrectionResult:
    model_name = model or _settings.qwen_model

    # Smoke-test / CI shortcut: skip the LLM call entirely.
    if _is_mock():
        return CorrectionResult(text=raw, changed=False, notes="mock", model="mock")

    rag_block = "\n".join(
        f"[{h.canon} {h.work_id} 卷{h.juan or '-'}] {h.passage}" for h in rag_hits
    ) or "(無相關經文)"

    user_msg = (
        f"# 上一句\n{prev_ctx or '(無)'}\n\n"
        f"# 下一句\n{next_ctx or '(無)'}\n\n"
        f"# 相關 CBETA 經文\n{rag_block}\n\n"
        f"# 待校正字幕\n{raw}\n\n"
        f"請只校正錯字,輸出 JSON。"
    )

    resp = _client().chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=512,
    )
    raw_out = resp.choices[0].message.content or "{}"
    try:
        obj = json.loads(raw_out)
    except json.JSONDecodeError:
        obj = {"text": raw, "changed": False, "notes": "json parse failed"}
    return CorrectionResult(
        text=obj.get("text", raw).strip() or raw,
        changed=bool(obj.get("changed", False)),
        notes=str(obj.get("notes", "")),
        model=model_name,
    )
