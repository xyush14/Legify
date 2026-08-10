-- 012_child_tables.sql — make a matter's contents durable.
--
-- THE PROBLEM THIS FIXES
-- public.cases (009) and public.note_sheets (011) are durable, but the three
-- things a matter actually contains — drafts, consultation recordings and vault
-- documents — lived only in SQLite at KANOON_CACHE_PATH. On Railway that volume
-- is not guaranteed, so a lawyer could lose every draft on a deploy, and the
-- readiness rule (which counts drafts and documents) would silently regress a
-- "Ready" file back to "Draft pending". Same reason a diary must not live on a
-- notepad you might leave in the car.
--
-- WHAT IS DURABLE vs WHAT IS CACHE
-- Durable here: the row itself — text, metadata, and the case_id link. That is
-- everything the folder, the readiness rule and the note sheet read.
-- Deliberately NOT here: page images, embedding vectors and the FTS index. They
-- are derived from full_text/the upload, they are large, and they can be rebuilt.
-- They stay in the local SQLite cache. A cold machine loses only speed, not work.
--
-- Keyword search is provided in Postgres by a generated tsvector + GIN index, so
-- the Document Vault still searches when running on Postgres.
--
-- SAFETY: purely additive. Every statement is CREATE ... IF NOT EXISTS or an
-- ADD COLUMN IF NOT EXISTS. No DROP, no data change, safe to re-run.
--
-- RLS matches 008/009/011: enabled, no policies — only the service-role key
-- (used by the API, which scopes every query by user_id) can read.

-- ------------------------------------------------------------------ drafts
create table if not exists public.drafts (
    id                text primary key,          -- uuid4 hex, minted by the app
    user_id           uuid references auth.users (id) on delete cascade,
    case_id           uuid references public.cases (id) on delete set null,
    story_id          text not null,
    template_version  integer not null default 1,
    lang              text not null default 'en',
    answers_json      jsonb not null default '{}'::jsonb,
    title             text,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    exported_at       timestamptz,
    exported_format   text
);
create index if not exists idx_drafts_user_updated on public.drafts (user_id, updated_at desc);
create index if not exists idx_drafts_case         on public.drafts (case_id);

-- ----------------------------------------------------------- consultations
create table if not exists public.consultations (
    id            text primary key,
    user_id       uuid references auth.users (id) on delete cascade,
    case_id       uuid references public.cases (id) on delete set null,
    title         text,
    matter_type   text,
    parties       text,
    court         text,
    lang          text,
    duration_sec  integer,
    consent       boolean not null default false,
    transcript    text,
    report_json   jsonb not null default '{}'::jsonb,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
create index if not exists idx_consults_user_created on public.consultations (user_id, created_at desc);
create index if not exists idx_consults_case         on public.consultations (case_id);

-- --------------------------------------------------------------- documents
create table if not exists public.documents (
    id                text primary key,
    user_id           uuid references auth.users (id) on delete cascade,
    case_id           uuid references public.cases (id) on delete set null,
    title             text not null,
    doc_type          text,
    original_filename text,
    mime              text,
    page_count        integer not null default 1,
    full_text         text not null default '',
    metadata_json     jsonb not null default '{}'::jsonb,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create index if not exists idx_docs_user_updated on public.documents (user_id, updated_at desc);
create index if not exists idx_docs_case         on public.documents (case_id);

-- Keyword search, the Postgres way: a stored tsvector kept in step with the row
-- by the database itself, so there is no index to forget to update.
alter table public.documents
    add column if not exists search_tsv tsvector
    generated always as (
        to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(full_text, ''))
    ) stored;
create index if not exists idx_docs_search on public.documents using gin (search_tsv);

-- ------------------------------- research saved against a matter (008 gap)
-- case_folder returned "caselaw": [] because saved_caselaw had no matter link,
-- so "the law we found for this case" could not live in the case.
alter table public.saved_caselaw
    add column if not exists matter_id uuid references public.cases (id) on delete set null;
create index if not exists idx_saved_caselaw_matter on public.saved_caselaw (matter_id);

-- ---------------------------------------------------------------------- RLS
alter table public.drafts        enable row level security;
alter table public.consultations enable row level security;
alter table public.documents     enable row level security;
