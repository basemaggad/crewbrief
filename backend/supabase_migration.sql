-- ============================================================================
-- CrewBrief — supplemental migration
-- Run this in Supabase SQL Editor AFTER the initial schema.
-- It adds:
--   1) The match_chunks RPC for fast pgvector similarity search
--   2) The session_invalidations table (if missing)
--   3) Indexes for retrieval performance
-- Safe to run multiple times — uses IF NOT EXISTS / OR REPLACE.
-- ============================================================================

-- Enable extension if not already enabled
create extension if not exists vector;

-- ── session_invalidations (in case it wasn't in the initial schema) ─────────
create table if not exists session_invalidations (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(id) on delete cascade,
    document_name text not null,
    revision text,
    section text,
    message text,
    created_at timestamptz not null default now()
);

create index if not exists session_invalidations_session_id_idx
    on session_invalidations(session_id);

-- ── Index for chunk retrieval ───────────────────────────────────────────────
-- IVFFlat index on the embedding column, scoped by organization.
-- Lists=100 is a reasonable default for small-to-medium libraries.
create index if not exists document_chunks_embedding_idx
    on document_chunks
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

create index if not exists document_chunks_org_idx
    on document_chunks(organization_id);

create index if not exists document_chunks_doc_idx
    on document_chunks(document_id);

-- ── match_chunks RPC ────────────────────────────────────────────────────────
-- Used by query_service.py for pgvector cosine similarity search.
-- The embedding dimension here MUST match what embedding_service.py produces (1024).
create or replace function match_chunks(
    query_embedding vector(1024),
    match_organization_id uuid,
    match_count int default 8
)
returns table (
    id uuid,
    document_id uuid,
    content text,
    page_start int,
    page_end int,
    similarity float
)
language sql stable
as $$
    select
        dc.id,
        dc.document_id,
        dc.content,
        dc.page_start,
        dc.page_end,
        1 - (dc.embedding <=> query_embedding) as similarity
    from document_chunks dc
    where dc.organization_id = match_organization_id
    order by dc.embedding <=> query_embedding
    limit match_count;
$$;
