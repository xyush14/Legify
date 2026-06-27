-- migrations/006_user_profiles_welcome_sent.sql
--
-- Adds the welcome-email dedupe flag on public.user_profiles.
--
-- Without this column, the atomic-claim UPDATE in
-- headnote/api/onboarding.py:_claim_welcome silently 400s, the claim
-- returns False, and the endpoint reports {"sent": false,
-- "reason": "already_sent"} without ever contacting Resend. Result: no
-- welcome email fires on any new signup.
--
-- Schema:
--   welcome_sent BOOLEAN — flipped to TRUE the moment the atomic claim
--     wins. NULL/FALSE means "not yet sent". The conditional UPDATE filter
--     ``welcome_sent=not.is.true`` matches both NULL and FALSE.
--
-- Idempotent — safe to re-run.

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN;

-- Backfill: for every user with an active subscription that's NOT demo
-- (i.e. they've been around long enough to have hit a paywall), mark
-- welcome_sent = TRUE so we don't spam them with a delayed welcome the
-- next time they sign in. New users (plan='demo') stay NULL → eligible.
UPDATE public.user_profiles p
   SET welcome_sent = TRUE
  FROM public.subscriptions s
 WHERE p.id = s.user_id
   AND s.plan IN ('weekly', 'monthly', 'yearly', 'founder', 'partner')
   AND (p.welcome_sent IS NULL OR p.welcome_sent = FALSE);

-- Partial index to make the atomic-claim UPDATE cheap.
CREATE INDEX IF NOT EXISTS idx_user_profiles_welcome_pending
  ON public.user_profiles (id)
  WHERE welcome_sent IS NOT TRUE;
