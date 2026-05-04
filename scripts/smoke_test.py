"""End-to-end smoke test driver.

Exercises the full pipeline against running backend + worker + infra:

  upload → VAD → transcribe (mock) → dict_pass → rag_correct (mock) →
  review (auto-resume) → SRT

Asserts:
  * Each pipeline step ends in 'completed' (or 'skipped' for review).
  * At least one segment was produced.
  * dict_pass actually corrects the seeded mishears (般弱→般若 etc.).
  * SRT download is non-empty and well-formed.

Usage:
  python scripts/smoke_test.py /tmp/smoke.mp3
  python scripts/smoke_test.py /tmp/smoke.mp3 --api http://localhost:8000

Exits 0 on success, non-zero with a readable error otherwise.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import urllib.request
import urllib.error
import json


def _http(method: str, url: str, body: dict | bytes | None = None,
          headers: dict | None = None, timeout: float = 30.0) -> tuple[int, bytes]:
    data: bytes | None
    h = dict(headers or {})
    if isinstance(body, dict):
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    else:
        data = body
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _json(method: str, url: str, body: dict | None = None) -> dict:
    code, raw = _http(method, url, body=body)
    if code >= 400:
        raise RuntimeError(f"{method} {url} → {code}: {raw[:500]!r}")
    return json.loads(raw or b"{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", help="Path to MP3 to upload")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--timeout", type=int, default=300, help="Overall pipeline timeout (s)")
    args = ap.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        print(f"[FAIL] audio file not found: {audio_path}", file=sys.stderr)
        return 2

    api = args.api.rstrip("/")
    print(f"[smoke] api={api}  audio={audio_path}  size={audio_path.stat().st_size}B")

    # 1. /uploads/init
    init = _json("POST", f"{api}/uploads/init", {
        "filename": audio_path.name,
        "content_type": "audio/mpeg",
    })
    audio_key = init["audio_key"]
    upload_url = init["upload_url"]
    print(f"[smoke] upload_url issued; audio_key={audio_key}")

    # 2. PUT to presigned S3 url. If the URL points at a Docker-internal
    # hostname (e.g. "minio"), rewrite to localhost so the test host can reach
    # MinIO. When backend already issues a localhost URL this is a no-op.
    parsed = urlparse(upload_url)
    if parsed.hostname == "minio":
        upload_url = parsed._replace(netloc=f"localhost:{parsed.port or 9000}").geturl()

    body = audio_path.read_bytes()
    code, _ = _http("PUT", upload_url, body=body, headers={"Content-Type": "audio/mpeg"}, timeout=60)
    if code >= 400:
        print(f"[FAIL] PUT upload returned {code}", file=sys.stderr)
        return 3
    print(f"[smoke] uploaded {len(body)} bytes")

    # 3. /jobs
    job = _json("POST", f"{api}/jobs", {
        "name": "smoke-test",
        "audio_key": audio_key,
        "config": {},
    })
    job_id = job["id"]
    print(f"[smoke] job created: {job_id}")

    # 4. Poll until terminal, auto-resume review.
    review_resumed = False
    deadline = time.time() + args.timeout
    last_log = ""
    while time.time() < deadline:
        j = _json("GET", f"{api}/jobs/{job_id}")
        steps = {s["name"]: s for s in j["steps"]}
        # Compose a one-line status to print on change
        line = " | ".join(
            f"{n}:{s['status']}/{int(s['progress']*100)}%" for n, s in steps.items()
        )
        if line != last_log:
            print(f"[smoke] {j['status']:10s} {line}")
            last_log = line

        # Auto-resume review.
        review = steps.get("review")
        if review and review["status"] == "paused" and not review_resumed:
            print("[smoke] review paused → auto-resume")
            _http("POST", f"{api}/jobs/{job_id}/steps/review/action",
                  body={"action": "resume"})
            review_resumed = True

        if j["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(2)

    if j["status"] != "completed":
        print(f"[FAIL] job did not complete: status={j['status']} error={j.get('error')}",
              file=sys.stderr)
        for s in j["steps"]:
            print(f"  - {s['name']}: status={s['status']} log={(s.get('log') or '')[-300:]!r}",
                  file=sys.stderr)
        return 4

    # 5. Verify segments + dict-pass corrections.
    code, raw = _http("GET", f"{api}/jobs/{job_id}/segments")
    segs = json.loads(raw)
    if not segs:
        print("[FAIL] no segments produced", file=sys.stderr)
        return 5
    print(f"[smoke] segments produced: {len(segs)}")

    # Mock Whisper seeds 般弱波羅密 / 阿彌打 / 釋加 — dict_pass should fix them.
    joined_dict = "\n".join((s.get("text_dict") or s.get("text_raw") or "") for s in segs)
    bad_terms = ["般弱波羅密", "阿彌打佛", "釋加牟尼"]
    leaked = [t for t in bad_terms if t in joined_dict]
    if leaked:
        print(f"[FAIL] dict_pass did not correct: {leaked}", file=sys.stderr)
        print(f"[debug] dict text:\n{joined_dict}", file=sys.stderr)
        return 6
    must_have = ["般若波羅蜜", "阿彌陀佛", "釋迦牟尼"]
    missing = [t for t in must_have if t not in joined_dict]
    if missing:
        print(f"[FAIL] expected corrected terms missing: {missing}", file=sys.stderr)
        print(f"[debug] dict text:\n{joined_dict}", file=sys.stderr)
        return 7
    print(f"[smoke] dict_pass corrections OK ({must_have})")

    # 6. Verify all steps completed (or skipped).
    bad = [s for s in j["steps"] if s["status"] not in ("completed", "skipped")]
    if bad:
        print(f"[FAIL] non-completed steps: {[s['name'] for s in bad]}", file=sys.stderr)
        return 8

    # 7. SRT download.
    code, raw = _http("GET", f"{api}/jobs/{job_id}/srt")
    if code != 200 or len(raw) < 50:
        print(f"[FAIL] SRT download bad: code={code} bytes={len(raw)}", file=sys.stderr)
        return 9
    body = raw.decode("utf-8", errors="replace")
    if "-->" not in body:
        print(f"[FAIL] SRT body missing arrow:\n{body[:500]}", file=sys.stderr)
        return 10
    print(f"[smoke] SRT OK ({len(raw)} bytes, {body.count('-->')} cues)")

    print("[PASS] smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
