-- 013_client_intake.sql — the client document-intake link.
--
-- WHAT THIS IS FOR
-- One durable, write-only link per matter that a lawyer sends the client
-- ("send me your documents here"). The client opens it with NO login, uploads
-- photos/PDFs, and the files land in a PENDING TRAY — never in the case file.
-- The lawyer reviews each one and saves it to the file or discards it.
--
-- THE SAFETY PROPERTIES, AND WHY THE SHAPE IS LIKE THIS
--  • Write-only: the token grants upload on ONE matter and reads nothing back —
--    no documents, no order sheet, no other matter. A leaked link cannot leak
--    the client's case; the worst it can do is put junk in a tray.
--  • Stateful token (a row here, not a signed blob) precisely so it can be
--    REVOKED instantly. Stateless HMAC links — the pattern in
--    headnote/cases/daily_links.py — cannot be withdrawn once sent.
--  • NO expiry by default (expires_at is nullable). An Indian case runs for
--    years; a link that dies in a fortnight means the lawyer re-sends it
--    constantly and stops using the feature. Risk is held down by write-only +
--    revoke + the approval gate instead. A lawyer may still set an expiry.
--  • Nothing auto-files: `status` starts 'pending', so a stranger with the link
--    can never inject a document into the record.
--  • Provenance is kept (who said they were uploading, when, from which link)
--    because a document in a court file must have a known origin.
--
-- Bytes do NOT live here. They go to a PRIVATE Supabase Storage bucket and this
-- row keeps the object path: a client's original is the only copy, so it cannot
-- sit on an ephemeral disk, and Postgres is the wrong place for blobs.
--
-- SAFETY: purely additive — CREATE ... IF NOT EXISTS only. No DROP, no data
-- change, safe to re-run. RLS enabled with no policies, matching 008/009/011/012:
-- only the service-role key (the API, which scopes every query by user_id) reads.

create table if not exists public.intake_links (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references auth.users (id) on delete cascade,
    case_id      uuid not null references public.cases (id) on delete cascade,
    token        text not null unique,        -- opaque, high-entropy; the whole URL secret
    label        text,                        -- e.g. "Client — Rahul Verma"
    expires_at   timestamptz,                 -- NULL = lives as long as the matter
    max_per_day  integer not null default 20, -- abuse brake, not a usage limit
    revoked_at   timestamptz,
    created_at   timestamptz not null default now(),
    last_used_at timestamptz
);

-- One ACTIVE link per matter: rotating a link revokes the old one, so a lawyer
-- never has two live links to the same file and cannot lose track of what is out.
create unique index if not exists idx_intake_links_active
    on public.intake_links (user_id, case_id)
    where revoked_at is null;
create index if not exists idx_intake_links_token on public.intake_links (token);

create table if not exists public.intake_uploads (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null references auth.users (id) on delete cascade,
    case_id        uuid not null references public.cases (id) on delete cascade,
    link_id        uuid references public.intake_links (id) on delete set null,
    filename       text,
    mime           text,
    size_bytes     integer,
    object_path    text,                      -- path in the private Storage bucket
    note           text,                      -- what the client says this is
    uploader_name  text,
    uploader_phone text,
    status         text not null default 'pending',   -- pending | saved | discarded
    document_id    text,                      -- the vault row, once saved
    created_at     timestamptz not null default now(),
    reviewed_at    timestamptz
);

create index if not exists idx_intake_uploads_case
    on public.intake_uploads (user_id, case_id, status);
create index if not exists idx_intake_uploads_pending
    on public.intake_uploads (user_id, status, created_at desc);

alter table public.intake_links   enable row level security;
alter table public.intake_uploads enable row level security;
