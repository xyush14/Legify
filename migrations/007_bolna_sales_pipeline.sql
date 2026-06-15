-- 007_bolna_sales_pipeline.sql
-- Tables for Bolna voice-agent sales pipeline:
--   leads        — prospect funnel (one row per phone number we've ever pitched)
--   bolna_calls  — one row per outbound/inbound Bolna call (with transcript)
--   dnd_list     — do-not-call list (the agent writes to this on hostile/no_interest)
--
-- Mirrors the pattern from 006_whatsapp_bot.sql: service-role writes only,
-- RLS off (backend goes through SUPABASE_SERVICE_ROLE_KEY which bypasses RLS).

create table if not exists public.leads (
    id            uuid primary key default gen_random_uuid(),
    phone         text not null unique,
    name          text,
    practice_area text,
    city          text,
    court         text,
    source        text,
    status        text not null default 'new'
                  check (status in ('new', 'contacted', 'interested',
                                    'demo_booked', 'trial_started',
                                    'converted', 'dnd', 'unreachable')),
    user_id       uuid references auth.users(id),
    last_call_id  text,
    last_contact_at timestamptz,
    notes         text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists leads_phone_idx  on public.leads(phone);
create index if not exists leads_status_idx on public.leads(status);


create table if not exists public.bolna_calls (
    id                uuid primary key default gen_random_uuid(),
    call_id           text not null unique,  -- Bolna's external call id
    lead_id           uuid references public.leads(id),
    phone             text not null,
    direction         text not null default 'outbound'
                      check (direction in ('outbound', 'inbound')),
    status            text not null
                      check (status in ('initiated', 'ringing', 'in_progress',
                                        'completed', 'failed', 'no_answer', 'busy')),
    outcome           text check (outcome in ('booked_demo', 'sent_whatsapp',
                                              'trial_started', 'dnd', 'no_outcome')),
    duration_seconds  int,
    transcript        text,
    summary           text,
    recording_url     text,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create index if not exists bolna_calls_lead_id_idx    on public.bolna_calls(lead_id);
create index if not exists bolna_calls_phone_idx      on public.bolna_calls(phone);
create index if not exists bolna_calls_created_at_idx on public.bolna_calls(created_at desc);


create table if not exists public.dnd_list (
    phone     text primary key,
    reason    text not null,
    marked_at timestamptz not null default now(),
    marked_by text default 'bolna_agent'
);


-- Reusable updated_at trigger (only create if not already present from earlier migrations)
do $$
begin
    if not exists (select 1 from pg_proc where proname = 'set_updated_at') then
        create function public.set_updated_at() returns trigger as $f$
        begin
            new.updated_at = now();
            return new;
        end;
        $f$ language plpgsql;
    end if;
end $$;

drop trigger if exists leads_updated_at on public.leads;
create trigger leads_updated_at before update on public.leads
    for each row execute function public.set_updated_at();

drop trigger if exists bolna_calls_updated_at on public.bolna_calls;
create trigger bolna_calls_updated_at before update on public.bolna_calls
    for each row execute function public.set_updated_at();
