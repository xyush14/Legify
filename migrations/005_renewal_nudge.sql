-- migrations/005_renewal_nudge.sql
--
-- Adds dedupe tracking for the "your plan expires in 3 days" nudge email.
-- One column on public.subscriptions:
--
--   renewal_nudge_sent_for_period_end TIMESTAMPTZ NULL
--     When the nudge fires, we stamp this with the subscription's current
--     period_end. The cron job skips any row where this column already
--     equals period_end (i.e., we already nudged for this billing cycle).
--
-- After a successful renewal, change_plan() sets a new period_end AND
-- clears this column to NULL, re-arming the nudge for the next cycle.
--
-- Idempotent — safe to re-run.

ALTER TABLE public.subscriptions
  ADD COLUMN IF NOT EXISTS renewal_nudge_sent_for_period_end TIMESTAMPTZ NULL;

-- Speeds up the cron's "find subs expiring in 2-4 days" scan.
CREATE INDEX IF NOT EXISTS idx_subscriptions_period_end_status
  ON public.subscriptions (period_end)
  WHERE status = 'active' AND plan IN ('weekly', 'monthly', 'yearly');
