-- migrations/004_partners_and_referrals.sql
--
-- Adds the channel-partner + referral-code system:
--   partners              one row per signed distributor (law house)
--   partner_employees     sub-reps under a partner, each gets their own subcode
--   referral_codes        the actual codes (distributor or publication)
--   referral_attributions which user applied which code (signup / checkout)
--   referral_events       commission ledger — written at Cashfree webhook PAID
--
-- Used by:
--   POST /api/payments/create-order   (apply discount + stash attribution)
--   POST /api/payments/webhook        (write event row on PAID)
--   GET  /api/payments/validate-referral
--   GET  /admin/partners              (built in a follow-up step)
--
-- Design decisions baked in (flip with a follow-up migration if needed):
--   * commission_pct lives on partners (cleaner ledger; events snapshot it
--     at write time, so historical math is preserved even if the rate changes)
--   * discount_pct lives on the code (lets one partner run multiple offers)
--   * applies_to = 'first_order' by default (5% off goes to the first paid
--     order only; renewals are full price). Set to 'all_orders' on the code
--     if you negotiate a perpetual deal.
--   * referral_events.order_id is UNIQUE → Cashfree webhook replay is safe
--
-- Idempotent — safe to re-run. Run in: Supabase dashboard -> SQL Editor.

-- ----------------------------------------------------------------------------
-- partners: distributors (law houses) signed via the appointment PDF
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.partners (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name              TEXT NOT NULL,
  contact_email     TEXT,           -- primary contact; used for self-referral guard
  contact_phone     TEXT,
  city              TEXT,
  state             TEXT,
  territory         TEXT,           -- free-text: 'Bhopal / MP-central'
  commission_pct    NUMERIC(5,2) NOT NULL DEFAULT 10.00
                    CHECK (commission_pct >= 0 AND commission_pct <= 100),
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','paused','terminated')),
  signed_at         TIMESTAMPTZ,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_partners_status ON public.partners(status);

-- ----------------------------------------------------------------------------
-- partner_employees: each sub-rep under a partner. No Headnote login —
-- represented purely by their own referral subcode.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.partner_employees (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id        UUID NOT NULL REFERENCES public.partners(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  email             TEXT,           -- used for self-referral guard
  phone             TEXT,
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','inactive')),
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_partner_employees_partner
  ON public.partner_employees(partner_id);

-- ----------------------------------------------------------------------------
-- referral_codes: WADHWA-ARJUN, EBC5, etc. One row per code.
--
-- kind='distributor': partner_id required; employee_id optional. discount_pct
--   is what the buyer saves; partner.commission_pct is what the partner earns.
-- kind='publication': partner_id is NULL, publication_name required. Pure
--   buyer discount, no commission (Headnote absorbs per the design decision).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.referral_codes (
  code              TEXT PRIMARY KEY,            -- stored uppercase; canonicalize on insert
  kind              TEXT NOT NULL
                    CHECK (kind IN ('distributor','publication')),
  partner_id        UUID REFERENCES public.partners(id) ON DELETE CASCADE,
  employee_id       UUID REFERENCES public.partner_employees(id) ON DELETE SET NULL,
  publication_name  TEXT,                        -- e.g. 'Eastern Book Company'
  discount_pct      NUMERIC(5,2) NOT NULL DEFAULT 0
                    CHECK (discount_pct >= 0 AND discount_pct <= 100),
  applies_to        TEXT NOT NULL DEFAULT 'first_order'
                    CHECK (applies_to IN ('first_order','all_orders')),
  active            BOOLEAN NOT NULL DEFAULT TRUE,
  expires_at        TIMESTAMPTZ,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT referral_codes_ownership CHECK (
    (kind = 'distributor' AND partner_id IS NOT NULL)
    OR (kind = 'publication' AND publication_name IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_referral_codes_partner
  ON public.referral_codes(partner_id) WHERE partner_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_referral_codes_employee
  ON public.referral_codes(employee_id) WHERE employee_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_referral_codes_active
  ON public.referral_codes(active) WHERE active = TRUE;

-- ----------------------------------------------------------------------------
-- referral_attributions: which user applied which code, when, from where.
-- Append-only. Multiple rows per user are fine — most recent wins at order
-- time (we read the code that was actually stamped on the Cashfree order).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.referral_attributions (
  id                BIGSERIAL PRIMARY KEY,
  user_id           UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  user_email        TEXT NOT NULL,
  code              TEXT NOT NULL REFERENCES public.referral_codes(code) ON DELETE CASCADE,
  partner_id        UUID,           -- denormalized for fast dashboard reads
  employee_id       UUID,           -- denormalized
  applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  source            TEXT NOT NULL DEFAULT 'checkout'
                    CHECK (source IN ('signup','checkout','admin'))
);

CREATE INDEX IF NOT EXISTS idx_referral_attributions_user
  ON public.referral_attributions(user_id);
CREATE INDEX IF NOT EXISTS idx_referral_attributions_code_applied
  ON public.referral_attributions(code, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_referral_attributions_partner
  ON public.referral_attributions(partner_id) WHERE partner_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- referral_events: the commission ledger. One row per Cashfree PAID order
-- that carried a code. Idempotent on order_id so webhook replay is safe.
--
-- commission_pct is SNAPSHOTTED at event-write time from partners.commission_pct.
-- That means if you bump a partner's tier from 10% → 15%, old events keep their
-- 10% and new events get 15% — historical payouts stay correct.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.referral_events (
  id                BIGSERIAL PRIMARY KEY,
  order_id          TEXT NOT NULL UNIQUE,    -- Cashfree order_id
  user_id           UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  user_email        TEXT,
  code              TEXT NOT NULL REFERENCES public.referral_codes(code) ON DELETE CASCADE,
  partner_id        UUID,           -- denormalized for dashboard queries
  employee_id       UUID,
  plan_id           TEXT NOT NULL,
  gross_amount_inr  NUMERIC(10,2) NOT NULL,    -- list price before discount
  discount_inr      NUMERIC(10,2) NOT NULL DEFAULT 0,
  net_amount_inr    NUMERIC(10,2) NOT NULL,    -- what the user actually paid
  commission_pct    NUMERIC(5,2) NOT NULL DEFAULT 0,
  commission_inr    NUMERIC(10,2) NOT NULL DEFAULT 0,
  payout_status     TEXT NOT NULL DEFAULT 'pending'
                    CHECK (payout_status IN ('pending','paid','reversed','none')),
  payout_id         TEXT,
  payout_at         TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_referral_events_partner_created
  ON public.referral_events(partner_id, created_at DESC) WHERE partner_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_referral_events_employee_created
  ON public.referral_events(employee_id, created_at DESC) WHERE employee_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_referral_events_payout_status
  ON public.referral_events(payout_status, created_at);
CREATE INDEX IF NOT EXISTS idx_referral_events_code_created
  ON public.referral_events(code, created_at DESC);

-- ============================================================================
-- ROW LEVEL SECURITY
-- Backend writes via service-role key (bypasses RLS). No client-facing reads
-- on these tables yet — hard-deny anon/auth by enabling RLS with no policy.
-- ============================================================================

ALTER TABLE public.partners              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_employees     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.referral_codes        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.referral_attributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.referral_events       ENABLE ROW LEVEL SECURITY;
