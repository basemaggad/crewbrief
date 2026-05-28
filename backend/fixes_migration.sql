-- ============================================================================
-- CrewBrief — fixes_migration.sql
-- Run in Supabase SQL Editor. Idempotent (safe to run more than once).
--
-- Addresses:
--   Blocker 1 — auth.py looks up users.organization_id / users.role for every
--               request; if that row is missing, every call 403s.
--   Blocker 2 — embedding dimension must be 1024 to match embedding_service.py
--               and the match_chunks RPC.
--   500 MB    — raise the Storage bucket file-size limit.
--
-- IMPORTANT: the repo's 001_initial_schema.sql was a directory-tree dump, not
-- SQL, so the live schema for users/organizations/document_chunks could not be
-- verified from code. This file is written from auth.py's expectations. RUN
-- SECTION 0 FIRST and eyeball the output before applying the rest.
-- ============================================================================


-- ── 0. DIAGNOSTICS (read-only — run these first) ────────────────────────────
-- What tables exist?
select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;

-- Does users have the columns auth.py needs?
select column_name, data_type
from information_schema.columns
where table_schema = 'public' and table_name = 'users'
order by ordinal_position;

-- What dimension is the embedding column? (want: vector(1024))
select a.attname, format_type(a.atttypid, a.atttypmod) as type
from pg_attribute a
join pg_class c on c.oid = a.attrelid
where c.relname = 'document_chunks' and a.attname = 'embedding';

-- Current bucket size limit (bytes)
select id, name, file_size_limit, public from storage.buckets where id = 'documents';


-- ── 1. Organizations + users profile tables ─────────────────────────────────
create table if not exists organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null default 'Royal Jordanian',
    created_at timestamptz not null default now()
);

-- Ensure at least one organization exists.
insert into organizations (name)
select 'Royal Jordanian'
where not exists (select 1 from organizations);

create table if not exists users (
    id uuid primary key references auth.users(id) on delete cascade,
    email text,
    organization_id uuid references organizations(id),
    role text not null default 'pilot',
    created_at timestamptz not null default now()
);

-- If users already existed but was missing columns, add them.
alter table users add column if not exists organization_id uuid references organizations(id);
alter table users add column if not exists role text not null default 'pilot';
alter table users add column if not exists email text;


-- ── 2. Backfill: every auth user needs a profile row ────────────────────────
insert into users (id, email, organization_id, role)
select au.id,
       au.email,
       (select id from organizations order by created_at limit 1),
       'pilot'
from auth.users au
where not exists (select 1 from users u where u.id = au.id);

-- Patch any existing profile rows that have no org assigned.
update users
set organization_id = (select id from organizations order by created_at limit 1)
where organization_id is null;


-- ── 3. Auto-create a profile when a new auth user signs up ──────────────────
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.users (id, email, organization_id, role)
    values (
        new.id,
        new.email,
        (select id from public.organizations order by created_at limit 1),
        'pilot'
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function handle_new_user();


-- ── 4. Embedding dimension (NO destructive change applied automatically) ────
-- embedding_service.py emits 1024-dim vectors; match_chunks expects vector(1024).
-- If the diagnostic in section 0 shows a different dimension (e.g. 1536), the
-- column must be recreated — which DROPS existing chunk vectors. Only run this
-- if the dimension is actually wrong, then re-create the ivfflat index from
-- supabase_migration.sql:
--
--   alter table document_chunks drop column embedding;
--   alter table document_chunks add column embedding vector(1024);
--   create index if not exists document_chunks_embedding_idx
--       on document_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);


-- ── 5. Storage: raise the per-file limit to 500 MB ──────────────────────────
-- 500 MB = 524288000 bytes.
-- NOTE: a project-wide upload cap and your Supabase plan also apply. Verify in
-- Dashboard → Storage → Settings; the free tier caps file size well below this,
-- so 500 MB uploads require a plan that supports it.
insert into storage.buckets (id, name, file_size_limit, public)
select 'documents', 'documents', 524288000, false
where not exists (select 1 from storage.buckets where id = 'documents');

update storage.buckets
set file_size_limit = 524288000
where id = 'documents';


-- ── 6. VERIFY (read-only — run after applying) ──────────────────────────────
select 'auth users' as label, count(*) as n from auth.users
union all
select 'profile rows', count(*) from users
union all
select 'profiles missing org', count(*) from users where organization_id is null;
