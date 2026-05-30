-- migrations/003_assist_requests.sql
--
-- Persists every personal-assist request as a worked queue item.
--
-- Before this table the "Not satisfied? our team will help" CTA was
-- fire-and-forget: it emailed the founder and forgot. Now each request is
-- also stored here so it survives a missed/deleted email, can be worked
-- from a backend queue (/admin/assist), and carries a status the founder
-- can move open -> answered -> closed.
--
-- Used by:
--   POST /api/assist/research, /api/assist/draft   (headnote/api/assist.py — writes a row)
--   GET  /admin/assist/requests                    (headnote/api/admin.py — lists the queue)
--   POST /admin/assist/requests/{id}/resolve       (headnote/api/admin.py — mark answered/closed)
--
-- Idempotent — safe to run multiple times. Run in: Supabase dashboard -> SQL Editor -> paste -> Run.

CREATE TABLE IF NOT EXISTS public.assist_requests (
  id              BIGSERIAL PRIMARY KEY,
  -- Nullable so a request is never lost if the user row is later deleted;
  -- the denormalised email/name/phone below keep it actionable regardless.
  user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  user_email      TEXT NOT NULL,
  user_name       TEXT,
  user_phone      TEXT,
  mode            TEXT NOT NULL DEFAULT 'research'
                  CHECK (mode IN ('research', 'draft')),
  query           TEXT NOT NULL,        -- what the lawyer asked for
  source_context  TEXT,                 -- their last research query / page context
  status          TEXT NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open', 'answered', 'closed')),
  answer_note     TEXT,                 -- what case-law / notes the founder delivered
  answered_by     TEXT,                 -- who resolved it (shared admin token -> 'admin')
  answered_at     TIMESTAMPTZ,
  email_sent      BOOLEAN NOT NULL DEFAULT FALSE,  -- did the Resend alert fire?
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The queue is read newest-open-first; index for that and for per-user history.
CREATE INDEX IF NOT EXISTS idx_assist_status_created
  ON public.assist_requests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assist_user
  ON public.assist_requests (user_id);

-- Backend uses the service-role key (bypasses RLS), so no policies are needed
-- for the admin queue. Enable RLS with no policy to hard-deny anon/auth roles
-- in case the anon key ever touches this table by mistake.
ALTER TABLE public.assist_requests ENABLE ROW LEVEL SECURITY;
