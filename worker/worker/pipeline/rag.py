"""CBETA RAG retrieval — find scripture passages relevant to a subtitle segment.

Embeddings live in Postgres (pgvector). Ingestion is in scripts/ingest_cbeta.py.
At runtime we embed the query (one row at a time), do cosine search, and return
the top-k passages.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import text

from worker.config import get_settings
from worker.db import Session

_settings = get_settings()


def _is_mock() -> bool:
    return os.environ.get("MOCK_AI", "").lower() in ("1", "true", "yes")


@dataclass
class CbetaHit:
    canon: str          # T / X / ...
    work_id: str        # T0220
    juan: int | None
    passage: str
    score: float


def embed(texts: list[str]) -> list[list[float]]:
    """Returns dense vectors. Uses DashScope text-embedding-v3 by default."""
    if _settings.embedding_backend == "dashscope":
        from openai import OpenAI

        client = OpenAI(api_key=_settings.dashscope_api_key, base_url=_settings.dashscope_base_url)
        resp = client.embeddings.create(model=_settings.embedding_model, input=texts)
        return [d.embedding for d in resp.data]

    if _settings.embedding_backend == "bge-m3":
        from sentence_transformers import SentenceTransformer

        global _bge
        try:
            _bge
        except NameError:
            _bge = SentenceTransformer("BAAI/bge-m3")
        return _bge.encode(texts, normalize_embeddings=True).tolist()

    raise ValueError(f"unknown EMBEDDING_BACKEND={_settings.embedding_backend}")


def search(query: str, top_k: int = 4) -> list[CbetaHit]:
    if not query.strip():
        return []
    # Smoke-test / CI shortcut: skip embedding + pgvector lookup entirely.
    if _is_mock():
        return []
    vec = embed([query])[0]
    sql = text(
        """
        SELECT canon, work_id, juan, passage,
               1 - (embedding <=> CAST(:vec AS vector)) AS score
        FROM cbeta_chunks
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :k
        """
    )
    with Session() as s:
        rows = s.execute(sql, {"vec": vec, "k": top_k}).all()
    return [
        CbetaHit(canon=r.canon, work_id=r.work_id, juan=r.juan, passage=r.passage, score=float(r.score))
        for r in rows
    ]
