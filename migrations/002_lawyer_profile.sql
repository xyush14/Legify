-- migrations/002_lawyer_profile.sql
--
-- Adds the bar-association persona columns to public.user_profiles.
-- Each Headnote user can have ONE persona which auto-fills every draft's
-- signature block, vakalatnama, and home-court default.
--
-- Used by:
--   GET  /api/lawyer-profile  (headnote/api/lawyer_profile.py)
--   PATCH /api/lawyer-profile
--   compose.py format_spec substitution: {{advocate.*}} tokens
--
-- Idempotent — safe to run multiple times via the `if not exists` guard.
--
-- Run in: Supabase dashboard → SQL Editor → paste → Run.

alter table public.user_profiles
  add column if not exists advocate_name    text,
  add column if not exists enrolment_number text,
  add column if not exists bar_council      text,
  add column if not exists chamber_address  text,
  add column if not exists home_court       text;

-- Optional: a partial index for fast persona-completeness lookups in case
-- we later add an admin dashboard query like "how many users have completed
-- their bar profile". Skip if you don't need it yet.
-- create index if not exists user_profiles_persona_complete_idx
--   on public.user_profiles (id)
--   where advocate_name is not null and enrolment_number is not null;
