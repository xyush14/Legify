-- ============================================================================
-- Headnote subscription & entitlements schema (Supabase / Postgres)
-- Run this in Supabase SQL Editor once. Idempotent: safe to re-run.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- subscriptions: one row per user. Always exists once user signs up.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.subscriptions (
  user_id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  plan                 TEXT NOT NULL DEFAULT 'demo'
                       CHECK (plan IN ('demo', 'weekly', 'monthly', 'yearly')),
  status               TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active', 'expired', 'cancelled', 'past_due')),
  period_start         TIMESTAMPTZ NOT NULL DEFAULT now(),
  period_end           TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '14 days'),
  weekly_trial_used    BOOLEAN NOT NULL DEFAULT FALSE,
  payment_provider     TEXT,    -- razorpay | cashfree | manual | null
  payment_ref          TEXT,    -- provider-specific subscription/order id
  cancelled_at         TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_period_end ON public.subscriptions(period_end);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON public.subscriptions(status);

-- ----------------------------------------------------------------------------
-- usage_meters: one row per (user, feature, period). Counter-only, fast reads.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.usage_meters (
  id                   BIGSERIAL PRIMARY KEY,
  user_id              UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  feature              TEXT NOT NULL,  -- deep_search | draft | judgment_read | export_pdf
  period_key           TEXT NOT NULL,  -- 'lifetime' | '2026-W21' | '2026-05' | '2026' | '2026-05-19'
  used                 INTEGER NOT NULL DEFAULT 0,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, feature, period_key)
);

CREATE INDEX IF NOT EXISTS idx_meters_user ON public.usage_meters(user_id);

-- ----------------------------------------------------------------------------
-- usage_events: audit trail. One row per gated API call. Append-only.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.usage_events (
  id                   BIGSERIAL PRIMARY KEY,
  user_id              UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  feature              TEXT NOT NULL,
  cost_paise           INTEGER NOT NULL DEFAULT 0,
  model                TEXT,
  endpoint             TEXT,
  metadata             JSONB,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_user_created ON public.usage_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_created ON public.usage_events(created_at DESC);

-- ----------------------------------------------------------------------------
-- admin_users: grants admin role. Out-of-band only — no UI to insert.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.admin_users (
  user_id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role                 TEXT NOT NULL DEFAULT 'admin'
                       CHECK (role IN ('admin', 'support', 'viewer')),
  granted_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  granted_by           UUID REFERENCES auth.users(id),
  notes                TEXT
);

-- ----------------------------------------------------------------------------
-- payments: payment history (filled in once Razorpay/Cashfree wired in).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.payments (
  id                   BIGSERIAL PRIMARY KEY,
  user_id              UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  plan                 TEXT NOT NULL,
  amount_inr           INTEGER NOT NULL,
  currency             TEXT NOT NULL DEFAULT 'INR',
  provider             TEXT NOT NULL,  -- razorpay | cashfree | manual
  provider_payment_id  TEXT,
  provider_order_id    TEXT,
  status               TEXT NOT NULL,  -- created | authorized | captured | failed | refunded
  metadata             JSONB,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payments_user ON public.payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_provider_ref ON public.payments(provider, provider_payment_id);

-- ============================================================================
-- ROW LEVEL SECURITY
-- Users can only read their own subscription/meters/events. Backend uses
-- the service role key which bypasses RLS for writes.
-- ============================================================================

ALTER TABLE public.subscriptions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_meters   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_events   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments       ENABLE ROW LEVEL SECURITY;

-- Drop existing policies (so this migration stays idempotent)
DROP POLICY IF EXISTS "users read own subscription" ON public.subscriptions;
DROP POLICY IF EXISTS "users read own meters" ON public.usage_meters;
DROP POLICY IF EXISTS "users read own events" ON public.usage_events;
DROP POLICY IF EXISTS "users read own payments" ON public.payments;

CREATE POLICY "users read own subscription" ON public.subscriptions
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users read own meters" ON public.usage_meters
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users read own events" ON public.usage_events
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users read own payments" ON public.payments
  FOR SELECT USING (auth.uid() = user_id);

-- admin_users is only readable by service role (no policy = no client access)

-- ============================================================================
-- AUTO-PROVISION: every new auth.users row gets a Demo subscription.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.subscriptions (user_id, plan, status, period_start, period_end)
  VALUES (
    NEW.id,
    'demo',
    'active',
    now(),
    now() + interval '14 days'
  )
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================================
-- BACKFILL: existing users without a subscription row get one now.
-- ============================================================================

INSERT INTO public.subscriptions (user_id, plan, status, period_start, period_end)
SELECT
  u.id,
  'demo',
  'active',
  now(),
  now() + interval '14 days'
FROM auth.users u
LEFT JOIN public.subscriptions s ON s.user_id = u.id
WHERE s.user_id IS NULL;
