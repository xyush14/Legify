-- migrations/006_whatsapp_bot.sql
--
-- WhatsApp Business bot data model (v1).
-- Spec: docs/WHATSAPP_BOT_PRD.md §7
--
-- Convention note: Headnote keeps app-state in public.* tables that
-- reference auth.users(id) directly — there is no public.users table.
-- This migration follows that convention.
--
-- Three tables:
--
--   1) public.wa_users
--      Phone-number ↔ auth.users linkage written by the LINK flow
--      (OTPless OTP confirmation inside the WhatsApp DM). One phone
--      maps to one user. Absence of a row = unlinked free-tier phone.
--
--   2) public.wa_messages
--      Append-only log of every inbound + outbound message. Used for
--      debugging, abuse detection, and analytics. Body is redacted to
--      the first 500 chars at insert time (caller's responsibility).
--      Purge job runs daily, deletes rows older than 90 days.
--
--   3) public.wa_quota
--      Per-day query counter for unlinked / free-tier phones. Linked
--      paid users bypass this table entirely. Natural day rollover via
--      the (wa_phone, day) compound primary key — no reset job needed.
--
-- Idempotent — safe to re-run.

-- 1) Phone-to-account linkage
CREATE TABLE IF NOT EXISTS public.wa_users (
  wa_phone     TEXT PRIMARY KEY,                 -- canonical "+E.164", e.g. "+919876543210"
  user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  linked_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS wa_users_user_id_idx
  ON public.wa_users (user_id);

-- 2) Message log
CREATE TABLE IF NOT EXISTS public.wa_messages (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wa_phone     TEXT NOT NULL,
  direction    TEXT NOT NULL CHECK (direction IN ('in', 'out')),
  msg_type     TEXT NOT NULL,                    -- text, document, template, system, etc.
  body         TEXT,                             -- caller redacts to ~500 chars
  meta_msg_id  TEXT,                             -- provider's id (Meta or Twilio) — used for dedupe
  user_id      UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS wa_messages_phone_created_idx
  ON public.wa_messages (wa_phone, created_at DESC);

-- Dedupe support — providers retry on webhook ack failure; we must not double-process.
CREATE UNIQUE INDEX IF NOT EXISTS wa_messages_meta_msg_id_unique_idx
  ON public.wa_messages (meta_msg_id)
  WHERE meta_msg_id IS NOT NULL;

-- 3) Per-day quota
CREATE TABLE IF NOT EXISTS public.wa_quota (
  wa_phone     TEXT NOT NULL,
  day          DATE NOT NULL,                    -- IST day (Asia/Kolkata), computed by caller
  count        INT NOT NULL DEFAULT 0,
  PRIMARY KEY (wa_phone, day)
);

-- RLS — these tables are touched only by the service role from the bot
-- webhook. Disable RLS so the service role doesn't trip on policy gaps.
ALTER TABLE public.wa_users    DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.wa_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.wa_quota    DISABLE ROW LEVEL SECURITY;
