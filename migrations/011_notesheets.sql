-- 011_notesheets.sql — hearing note sheets.
--
-- WHY: the Home hub needs three things the schema didn't carry:
--   1. the court's PURPOSE for the next hearing (drives readiness),
--   2. an explicit PREPARED tick + the junior it is ASSIGNED to,
--   3. the note sheet itself — the advocate's hearing prep sheet.
--
-- (1) and (2) are small scalars, so they live inside public.cases.case_json
--     under the "prep" key — no ALTER on the live cases table, and both storage
--     backends already persist case_json verbatim (headnote/cases/storage.py
--     merge_prep()).
-- (3) is a real entity with its own lifecycle, so it gets this table.
--
-- One sheet per (user, matter, hearing_date): the sheet you carry to court on
-- the 12th is not the sheet you carry on the 23rd.
--
-- SAFETY: purely additive — every statement is CREATE ... IF NOT EXISTS or an
-- ALTER that only turns RLS on. There is no DROP, no data change, and running
-- it twice is a no-op.
--
-- RLS follows the same convention as 008/009: row level security is ENABLED and
-- no policy is created, so the anon/authenticated browser key can read nothing
-- directly. All access goes through the API using the service-role key, which
-- bypasses RLS and scopes every query by user_id.

create table if not exists public.note_sheets (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references auth.users (id) on delete cascade,
    case_id       uuid not null references public.cases (id) on delete cascade,
    hearing_date  text not null,                  -- ISO yyyy-mm-dd: the hearing this sheet is for
    source        text not null default 'junior', -- 'junior' | 'hand' (OCR of the written sheet)
    sheet_json    jsonb not null default '{}'::jsonb,
    ocr_engine    text,                           -- which reader produced a 'hand' sheet
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (user_id, case_id, hearing_date)
);

create index if not exists idx_notesheets_user_date
    on public.note_sheets (user_id, hearing_date);
create index if not exists idx_notesheets_case
    on public.note_sheets (case_id);

alter table public.note_sheets enable row level security;
