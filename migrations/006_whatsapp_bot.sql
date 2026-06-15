-- migrations/006_whatsapp_bot.sql
--
-- WhatsApp Business bot data model (v1).
-- Spec: docs/WHATSAPP_BOT_PRD.md §7
--
-- Three additions:
--
--   1) public.users.wa_phone + wa_linked_at
--      Links a WhatsApp phone number to an existing Headnote account.
--      Set via the LINK flow (OTPless OTP confirmation in WhatsApp DM).
--      One phone ↔ one user. NULL until the user runs LINK.
--
--   2) public.wa_messages
--      Append-only log of every inbound + outbound message. Used for
--      debugging, abuse detection, and analytics. Body redacted to
--      first 500 chars at insert time (caller's responsibility).
--      Purge job runs daily, deletes rows older than 90 days.
--
--   3) public.wa_quota
--      Per-day query counter for unlinked / free-tier phones. Linked
--      paid users bypass this table entirely. Natural day rollover via
--      the (wa_phone, day) compound primary key — no reset job needed.
--
-- Idempotent — safe to re-run.

-- 1) Link WhatsApp phone to existing user
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS wa_phone TEXT,
  ADD COLUMN IF NOT EXISTS wa_linked_at TIMESTAMPTZ;

-- E.164 uniqueness (one WA number = one user). Partial so multiple
-- NULL rows are allowed.
CREATE UNIQUE INDEX IF NOT EXISTS users_wa_phone_unique_idx
  ON public.users (wa_phone)
  WHERE wa_phone IS NOT NULL;

-- 2) Message log
CREATE TABLE IF NOT EXISTS public.wa_messages (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wa_phone     TEXT NOT NULL,
  direction    TEXT NOT NULL CHECK (direction IN ('in', 'out')),
  msg_type     TEXT NOT NULL,                  -- text, document, template, system
  body         TEXT,                           -- caller redacts to ~500 chars
  meta_msg_id  TEXT,                           -- id from Meta payload (for dedupe)
  user_id      UUID REFERENCES public.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS wa_messages_phone_created_idx
  ON public.wa_messages (wa_phone, created_at DESC);

-- Dedupe support — Meta retries on webhook ack failure, must not double-process.
CREATE UNIQUE INDEX IF NOT EXISTS wa_messages_meta_msg_id_unique_idx
  ON public.wa_messages (meta_msg_id)
  WHERE meta_msg_id IS NOT NULL;

-- 3) Per-day quota
CREATE TABLE IF NOT EXISTS public.wa_quota (
  wa_phone     TEXT NOT NULL,
  day          DATE NOT NULL,                  -- IST day (computed by caller in Asia/Kolkata)
  count        INT NOT NULL DEFAULT 0,
  PRIMARY KEY (wa_phone, day)
);

-- RLS — these tables are touched only by the service role from the bot
-- webhook. Disable RLS so the service role doesn't trip on policy gaps.
ALTER TABLE public.wa_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.wa_quota DISABLE ROW LEVEL SECURITY;
