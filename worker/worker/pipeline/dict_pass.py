"""Rule-based dictionary pre-pass.

Replaces common Whisper Cantonese mishears with the correct Buddhist term BEFORE
the LLM call — saves tokens and is deterministic. Dictionary lives in
data/dictionaries/buddhist_terms.json.

Format:
{
  "corrections": {"班若": "般若", "波羅密": "波羅蜜", ...},
  "patterns":    [{"re": "阿(?:喏|諾)多羅", "to": "阿耨多羅"}, ...]
}
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DICT_PATH = Path(__file__).resolve().parents[3] / "data" / "dictionaries" / "buddhist_terms.json"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, str], list[tuple[re.Pattern, str]]]:
    if not DICT_PATH.exists():
        return {}, []
    obj = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    corr: dict[str, str] = obj.get("corrections", {})
    patterns: list[tuple[re.Pattern, str]] = []
    for p in obj.get("patterns", []):
        patterns.append((re.compile(p["re"]), p["to"]))
    return corr, patterns


def apply_dict(text: str) -> tuple[str, list[dict]]:
    """Return (corrected_text, replacements_log)."""
    corr, patterns = _load()
    log: list[dict] = []
    out = text
    # plain replacements — longest-first so 般若波羅蜜多 wins over 般若
    for k in sorted(corr.keys(), key=len, reverse=True):
        if k in out:
            out = out.replace(k, corr[k])
            log.append({"from": k, "to": corr[k], "kind": "literal"})
    # regex patterns
    for pat, repl in patterns:
        if pat.search(out):
            out = pat.sub(repl, out)
            log.append({"from": pat.pattern, "to": repl, "kind": "regex"})
    return out, log
