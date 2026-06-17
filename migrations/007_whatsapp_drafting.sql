-- migrations/007_whatsapp_drafting.sql
--
-- WhatsApp drafting MVP (Phase 4a — bail §439 end-to-end via chat).
-- Spec: docs/WHATSAPP_BOT_PRD.md (Phase 4 — to be added)
--
-- Two tables:
--
--   1) public.wa_draft_sessions
--      Per-phone conversational state for the slot-collection flow.
--      One row per active draft-in-progress. Updated as the lawyer
--      answers each slot. Cleared on completion or 24h timeout.
--
--   2) public.wa_draft_tokens
--      Short-lived (24h) token → draft_id mapping so we can serve
--      PDFs / canvas links to a WhatsApp user without requiring
--      Supabase login. Single-use is NOT enforced — the same link
--      can be opened multiple times within its window.
--
-- Idempotent — safe to re-run.

-- 1) Conversational draft session
CREATE TABLE IF NOT EXISTS public.wa_draft_sessions (
  wa_phone        TEXT PRIMARY KEY,
  story_id        TEXT NOT NULL,                 -- 'bail_application', 'discharge_239', etc.
  next_slot       TEXT NOT NULL,                 -- 'court' | 'applicant_name' | … | 'review' | 'done'
  answers         JSONB NOT NULL DEFAULT '{}'::jsonb,
  draft_id        TEXT,                          -- set once the draft row has been created
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
);

CREATE INDEX IF NOT EXISTS wa_draft_sessions_expires_at_idx
  ON public.wa_draft_sessions (expires_at);

-- 2) Short-lived draft access tokens
CREATE TABLE IF NOT EXISTS public.wa_draft_tokens (
  token           TEXT PRIMARY KEY,              -- short uuid (e.g. base32 of uuid4 first 12 chars)
  draft_id        TEXT NOT NULL,
  wa_phone        TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
);

CREATE INDEX IF NOT EXISTS wa_draft_tokens_draft_id_idx
  ON public.wa_draft_tokens (draft_id);

CREATE INDEX IF NOT EXISTS wa_draft_tokens_expires_at_idx
  ON public.wa_draft_tokens (expires_at);

-- RLS off — service role only.
ALTER TABLE public.wa_draft_sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.wa_draft_tokens   DISABLE ROW LEVEL SECURITY;
