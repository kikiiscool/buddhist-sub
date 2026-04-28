"""CBETA TEI P5 → Postgres + pgvector ingestion.

Steps:
  1. Sparse-clone github.com/cbeta-org/xml-p5 (only the canon dirs we want)
  2. Walk *.xml, extract plain text from each work / juan
  3. Chunk into ~400-character passages (overlap 80 chars)
  4. Embed with DashScope (text-embedding-v3) or local bge-m3
  5. Upsert into table `cbeta_chunks`

Usage:
  python scripts/ingest_cbeta.py --canons T,X --limit-works 0
  python scripts/ingest_cbeta.py --canons T --limit-works 50  # quick smoke test

Re-running with the same content is idempotent (UPSERT on (canon, work_id, juan, chunk_idx)).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Bootstrap: load env so the script reads DATABASE_URL etc.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

REPO = "https://github.com/cbeta-org/xml-p5.git"
DEFAULT_CANONS = ["T", "X"]  # 大正藏, 卍續藏
CHUNK_CHARS = 400
CHUNK_OVERLAP = 80


@dataclass
class Chunk:
    canon: str
    work_id: str
    juan: int | None
    chunk_idx: int
    passage: str


def sparse_clone(target: Path, canons: list[str]) -> None:
    if target.exists():
        print(f"[clone] exists, pulling latest -> {target}")
        subprocess.run(["git", "-C", str(target), "pull", "--ff-only"], check=False)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[clone] sparse-cloning {REPO} canons={canons}")
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", REPO, str(target)],
        check=True,
    )
    subprocess.run(["git", "-C", str(target), "sparse-checkout", "init", "--cone"], check=True)
    subprocess.run(
        ["git", "-C", str(target), "sparse-checkout", "set", *canons],
        check=True,
    )
    subprocess.run(["git", "-C", str(target), "checkout"], check=True)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NOTE_RE = re.compile(r"<note[^>]*>.*?</note>", re.DOTALL)
_TEIHEADER_RE = re.compile(r"<teiHeader.*?</teiHeader>", re.DOTALL)


def xml_to_text(xml: str) -> str:
    """Quick TEI → plain text (good-enough for embedding; not a real TEI parser)."""
    s = _TEIHEADER_RE.sub("", xml)
    s = _NOTE_RE.sub("", s)
    s = _TAG_RE.sub("", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = _WS_RE.sub("", s)  # CBETA classical text — strip whitespace
    return s


def parse_filename(p: Path) -> tuple[str, str, int | None]:
    """Examples:
      T/T01/T01n0001_001.xml  -> canon=T, work=T0001, juan=1
      X/X09/X09n0240_002.xml -> canon=X, work=X0240, juan=2
    """
    name = p.stem  # T01n0001_001
    m = re.match(r"([A-Z]+)\d+n(\d+)_(\d+)$", name)
    if not m:
        m2 = re.match(r"([A-Z]+)\d+n(\d+)$", name)
        if m2:
            return m2.group(1), f"{m2.group(1)}{m2.group(2)}", None
        return p.parts[-3] if len(p.parts) >= 3 else "?", name, None
    canon, work_no, juan = m.group(1), m.group(2), int(m.group(3))
    return canon, f"{canon}{work_no}", juan


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    step = max(1, size - overlap)
    for i in range(0, len(text), step):
        piece = text[i : i + size]
        if piece:
            out.append(piece)
        if i + size >= len(text):
            break
    return out


def iter_chunks(repo_root: Path, canons: list[str], limit_works: int = 0) -> Iterator[Chunk]:
    work_count = 0
    seen_works: set[str] = set()
    for canon in canons:
        canon_dir = repo_root / canon
        if not canon_dir.exists():
            print(f"[warn] canon dir missing: {canon_dir}", file=sys.stderr)
            continue
        for xml_path in sorted(canon_dir.rglob("*.xml")):
            c, work_id, juan = parse_filename(xml_path)
            if work_id not in seen_works:
                seen_works.add(work_id)
                work_count += 1
                if limit_works and work_count > limit_works:
                    return
            try:
                xml = xml_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                print(f"[warn] read fail {xml_path}: {e}", file=sys.stderr)
                continue
            text = xml_to_text(xml)
            for idx, piece in enumerate(chunk_text(text)):
                yield Chunk(canon=c, work_id=work_id, juan=juan, chunk_idx=idx, passage=piece)


def embed_batch(texts: list[str]) -> list[list[float]]:
    backend = os.environ.get("EMBEDDING_BACKEND", "dashscope")
    if backend == "dashscope":
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ["DASHSCOPE_API_KEY"],
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL",
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            ),
        )
        # text-embedding-v3 limit: batch up to 10
        out: list[list[float]] = []
        for i in range(0, len(texts), 10):
            resp = client.embeddings.create(
                model=os.environ.get("EMBEDDING_MODEL", "text-embedding-v3"),
                input=texts[i : i + 10],
            )
            out.extend([d.embedding for d in resp.data])
        return out

    if backend == "bge-m3":
        from sentence_transformers import SentenceTransformer

        global _bge
        try:
            _bge
        except NameError:
            _bge = SentenceTransformer("BAAI/bge-m3")
        return _bge.encode(texts, normalize_embeddings=True).tolist()

    raise ValueError(f"unknown EMBEDDING_BACKEND={backend}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canons", default=",".join(DEFAULT_CANONS))
    ap.add_argument("--limit-works", type=int, default=0, help="0 = no limit (full canon)")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument(
        "--repo-dir",
        default="data/cbeta_xml",
        help="local path for sparse clone of cbeta-org/xml-p5",
    )
    args = ap.parse_args()
    canons = [c.strip() for c in args.canons.split(",") if c.strip()]

    repo_dir = Path(args.repo_dir)
    sparse_clone(repo_dir, canons)

    import psycopg2
    from pgvector.psycopg2 import register_vector

    db_url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    # convert SQLAlchemy URL → libpq
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    if db_url.startswith("postgresql://"):
        pass

    conn = psycopg2.connect(db_url)
    register_vector(conn)
    cur = conn.cursor()
    embed_dim = int(os.environ.get("EMBEDDING_DIM", "1024"))

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cbeta_chunks (
            id BIGSERIAL PRIMARY KEY,
            canon TEXT NOT NULL,
            work_id TEXT NOT NULL,
            juan INT,
            chunk_idx INT NOT NULL,
            passage TEXT NOT NULL,
            embedding vector({embed_dim}),
            UNIQUE(canon, work_id, juan, chunk_idx)
        );
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS cbeta_chunks_embedding_idx
        ON cbeta_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
        """
    )
    conn.commit()

    batch: list[Chunk] = []
    total = 0
    t0 = time.time()

    def flush(batch: list[Chunk]):
        nonlocal total
        if not batch:
            return
        vecs = embed_batch([c.passage for c in batch])
        rows = [
            (c.canon, c.work_id, c.juan, c.chunk_idx, c.passage, v)
            for c, v in zip(batch, vecs)
        ]
        from psycopg2.extras import execute_values

        execute_values(
            cur,
            """
            INSERT INTO cbeta_chunks (canon, work_id, juan, chunk_idx, passage, embedding)
            VALUES %s
            ON CONFLICT (canon, work_id, juan, chunk_idx) DO UPDATE
              SET passage = EXCLUDED.passage,
                  embedding = EXCLUDED.embedding;
            """,
            rows,
            template="(%s,%s,%s,%s,%s,%s::vector)",
        )
        conn.commit()
        total += len(batch)
        elapsed = time.time() - t0
        print(f"[ingest] +{len(batch)}  total={total}  rate={total/elapsed:.1f}/s")

    for ch in iter_chunks(repo_dir, canons, args.limit_works):
        batch.append(ch)
        if len(batch) >= args.batch:
            flush(batch)
            batch = []
    flush(batch)

    cur.close()
    conn.close()
    print(f"[done] {total} chunks ingested in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
