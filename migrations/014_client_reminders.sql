-- 014_client_reminders.sql — the log of hearing reminders sent to clients.
--
-- WHAT THIS IS FOR
-- The matters screen has asked for the client's mobile "for reminders" and taken
-- a tickbox consent to hearing reminders since the diary shipped, and nothing
-- ever sent one. This table is the record of the sends that now happen.
--
-- WHY A TABLE AND NOT JUST A LOG LINE
--  • The double-send guard. A lawyer who opens the reminder panel twice must not
--    message the same client twice about the same hearing — a second identical
--    message reads as a change of date and puts the client on the phone. The
--    unique index below makes the second send impossible rather than unlikely.
--  • Proof under the DPDP Act. We process a third party's phone number on the
--    strength of a consent the ADVOCATE recorded, so we keep what was sent, to
--    which number, when, on whose instruction, and the consent flag as it stood
--    at that moment. `consent_at_send` is stored rather than looked up later
--    precisely because the matter's consent flag can be changed afterwards.
--  • So the lawyer can see it happened. "Did my clerk remind him?" is the whole
--    question this feature answers, and it cannot be answered from a log file.
--
-- The message TEXT is stored as sent. It is short, it is the thing in dispute if
-- a client says he was told the wrong date, and re-deriving it later would give
-- the message the matter would produce TODAY, not the one that actually went.
--
-- SAFETY: purely additive — CREATE ... IF NOT EXISTS only. No DROP, no data
-- change, safe to re-run. RLS enabled with no policies, matching 008/009/011/012/013:
-- only the service-role key (the API, which scopes every query by user_id) reads.

create table if not exists public.client_reminders (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users (id) on delete cascade,
    case_id         uuid not null references public.cases (id) on delete cascade,

    -- WHICH hearing. ISO so it groups and compares; this is the field the
    -- double-send guard keys on, because "remind about the 13th" is the unit of
    -- work, not "remind this client".
    hearing_date    date not null,

    -- WHO was told, as at the moment of sending. Denormalised deliberately: the
    -- client's number in the matter may be corrected later, and this row must
    -- keep saying which number the message actually went to.
    client_name     text,
    to_phone        text not null,
    consent_at_send boolean not null default false,

    -- HOW it went out. 'whatsapp_template' = the approved utility template (the
    -- only lane Meta permits outside a 24h reply window); 'whatsapp_text' = free
    -- text, valid only inside that window; 'self' = the lawyer sent it himself
    -- from his own number and we recorded it so the guard and the audit hold.
    channel         text not null,
    lang            text,
    body            text,                        -- the message exactly as sent

    status          text not null default 'sent',  -- sent | failed
    provider        text,                          -- meta | twilio | self
    provider_msg_id text,
    error           text,                          -- why it failed, verbatim

    created_at      timestamptz not null default now()
);

-- THE DOUBLE-SEND GUARD. One SUCCESSFUL reminder per client-matter-hearing.
-- Scoped to status='sent' on purpose: a failed send must be retryable, and
-- without the predicate a single Meta timeout would lock that client out of
-- ever being reminded about that date.
create unique index if not exists idx_client_reminders_once
    on public.client_reminders (user_id, case_id, hearing_date)
    where status = 'sent';

create index if not exists idx_client_reminders_user_date
    on public.client_reminders (user_id, hearing_date desc);
create index if not exists idx_client_reminders_case
    on public.client_reminders (user_id, case_id, created_at desc);

alter table public.client_reminders enable row level security;
