-- migrations/009_matters.sql
--
-- Matters ("/matters" diary) — the lawyer's self-maintaining cause-list diary +
-- per-client case folders. Moves `cases` + `hearing_logs` OFF the ephemeral
-- server-side SQLite onto durable Supabase Postgres, so a lawyer's diary now
-- persists across deploys AND syncs across every device they log in from
-- (everything is scoped by user_id).
--
-- Used by:
--   headnote/cases/storage.py  (Supabase backend; falls back to SQLite locally)
--   headnote/api/cases.py      (all /api/cases/* endpoints)
--
-- Idempotent — safe to run multiple times. Run in: Supabase dashboard -> SQL
-- Editor -> paste -> Run.

CREATE TABLE IF NOT EXISTS public.cases (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Cascade: a diary has no meaning without its owner.
  user_id            UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  -- Real 16-char eCourts CNR, or a deterministic 'DY…' pseudo-key for a
  -- diary/manual matter that has no CNR yet. One row per (user, cnr).
  cnr                TEXT NOT NULL,
  -- Denormalised display columns (mirrors of fields inside case_json) so the
  -- list/board render without parsing the blob.
  case_title         TEXT,
  court_name         TEXT,          -- bench code OR the presiding judge's name (diary न्याया.)
  case_number        TEXT,
  case_year          TEXT,          -- kept as text ('' allowed; 2- or 4-digit)
  stage              TEXT,
  next_hearing_date  TEXT,          -- raw string as written; normalised to ISO in code for grouping
  -- The full normalised case dict (parties, client, sections, IAs, orders…).
  case_json          JSONB NOT NULL,
  source             TEXT,          -- 'diary' | 'ecourtsindia' | 'mock'
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- One row per case per user; enables upsert via on_conflict=user_id,cnr.
  CONSTRAINT uq_cases_user_cnr UNIQUE (user_id, cnr)
);

CREATE INDEX IF NOT EXISTS idx_cases_user_updated ON public.cases (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cases_user_number  ON public.cases (user_id, case_number);

-- Per-hearing outcome log (the diary's "what happened today" + rolled next date).
-- Its own rows (auditable history) rather than buried in case_json.
CREATE TABLE IF NOT EXISTS public.hearing_logs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  case_id            UUID NOT NULL REFERENCES public.cases(id) ON DELETE CASCADE,
  hearing_date       TEXT,          -- the date this outcome is for
  what_happened      TEXT,
  next_hearing_date  TEXT,          -- new next date set by this log
  stage              TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hlog_case ON public.hearing_logs (case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hlog_user ON public.hearing_logs (user_id);

-- Backend uses the service-role key (bypasses RLS). Enable RLS with no policy to
-- hard-deny the anon/auth roles in case the anon key ever touches these tables
-- by mistake (matches the convention in 003/008).
ALTER TABLE public.cases        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hearing_logs ENABLE ROW LEVEL SECURITY;
