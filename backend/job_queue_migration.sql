-- ============================================================================
-- CrewBrief — job_queue_migration.sql  (v2)
-- Run in Supabase SQL Editor BEFORE deploying the updated backend.
-- Idempotent — safe to run more than once, and safe to re-run over v1.
--
-- Creates / updates:
--   ingestion_jobs              one row per uploaded PDF
--   last_heartbeat_at column    lets the worker prove a long job is alive
--   claim_ingestion_job()       atomic claim; reclaims only DEAD jobs
--   sync_document_error_status  trigger: job 'error' => document 'error'
--   error_message on documents  added if not present
-- ============================================================================


-- ── 1. documents.error_message ──────────────────────────────────────────────
alter table documents add column if not exists error_message text;


-- ── 2. ingestion_jobs table ─────────────────────────────────────────────────
create table if not exists ingestion_jobs (
    id                uuid        primary key default gen_random_uuid(),
    document_id       uuid        not null references documents(id) on delete cascade,
    organization_id   uuid        not null,
    status            text        not null default 'pending'
                                  check (status in ('pending','processing','done','error')),
    attempts          int         not null default 0,
    max_attempts      int         not null default 3,
    error_message     text,
    created_at        timestamptz not null default now(),
    started_at        timestamptz,
    last_heartbeat_at timestamptz,
    completed_at      timestamptz
);

-- If ingestion_jobs already existed (v1), add the heartbeat column.
alter table ingestion_jobs add column if not exists last_heartbeat_at timestamptz;

create index if not exists ingestion_jobs_status_created_idx
    on ingestion_jobs (status, created_at)
    where status in ('pending','processing');

create index if not exists ingestion_jobs_document_id_idx
    on ingestion_jobs (document_id);


-- ── 3. claim_ingestion_job() — heartbeat-aware atomic claim ─────────────────
--
-- Reclaims a 'processing' job ONLY when its heartbeat is stale (the worker
-- crashed or was killed). A long-running but healthy job keeps beating, so
-- it is never reclaimed mid-flight — this is the fix for the "10-minute
-- timeout trap" where a large, legitimate PDF could be re-queued while still
-- being processed.
--
-- Heartbeat cadence (worker): every 30s.
-- Stale threshold here: 2 min  -> tolerates ~3 missed beats before reclaiming.
-- ============================================================================
create or replace function claim_ingestion_job()
returns setof ingestion_jobs
language plpgsql
as $$
begin
    -- Reclaim jobs whose worker has stopped heart-beating.
    update ingestion_jobs
    set status     = 'pending',
        started_at = null
    where status = 'processing'
      and coalesce(last_heartbeat_at, started_at) < now() - interval '2 minutes'
      and attempts < max_attempts;

    -- Atomically claim the oldest pending job and stamp an initial heartbeat.
    return query
    update ingestion_jobs
    set status            = 'processing',
        started_at        = now(),
        last_heartbeat_at = now(),
        attempts          = attempts + 1
    where id = (
        select id
        from   ingestion_jobs
        where  status   = 'pending'
          and  attempts < max_attempts
        order  by created_at
        limit  1
        for update skip locked
    )
    returning *;
end;
$$;


-- ── 4. Trigger: job 'error' => parent document 'error' ──────────────────────
-- Single source of truth. Whoever sets a job to terminal 'error' (the worker
-- now, or anything else later) automatically propagates to the document, so
-- the UI never gets stuck on 'processing'. Retries (status back to 'pending')
-- do NOT fire this, so the document stays 'processing' across retry attempts.
-- ============================================================================
create or replace function sync_document_error_status()
returns trigger
language plpgsql
as $$
begin
    if new.status = 'error' and (old.status is distinct from 'error') then
        update documents
        set status        = 'error',
            error_message  = coalesce(new.error_message, 'Ingestion failed')
        where id = new.document_id;
    end if;
    return new;
end;
$$;

drop trigger if exists ingestion_jobs_error_sync on ingestion_jobs;
create trigger ingestion_jobs_error_sync
    after update on ingestion_jobs
    for each row execute function sync_document_error_status();


-- ── 5. Grants ────────────────────────────────────────────────────────────────
grant all on ingestion_jobs to service_role;
grant execute on function claim_ingestion_job() to service_role;


-- ── 6. Verification ──────────────────────────────────────────────────────────
select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'ingestion_jobs'
  and column_name = 'last_heartbeat_at';

select routine_name from information_schema.routines
where routine_schema = 'public'
  and routine_name in ('claim_ingestion_job','sync_document_error_status')
order by routine_name;
