-- Postgres init: enable pgvector for CBETA embedding retrieval.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
