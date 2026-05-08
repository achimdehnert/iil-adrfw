-- mcp-hub rag_mcp schema (HYPOTHETICAL v1.0 implementation — using BIGINT)
-- This is intentionally wrong: it follows ADR-188 v1.0 which said BIGINT
-- but conflicts with all consumer-repos that use UUID.
-- iil-adrfw cross-repo validation should catch this.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_collections (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,                    -- WRONG per consumer-repo convention
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_documents (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,                    -- WRONG
    collection_id BIGINT REFERENCES rag_collections(id),
    title TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,                    -- WRONG
    document_id BIGINT REFERENCES rag_documents(id),
    chunk_text TEXT NOT NULL,
    embedding vector(1024),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_chunks_tenant ON rag_chunks (tenant_id);
