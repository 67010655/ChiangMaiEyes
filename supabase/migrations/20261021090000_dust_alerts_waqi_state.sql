-- Dust alerts from live WAQI sensors. WAQI terms forbid redistributing cached
-- or archived data, so no sensor reading is stored: the send log loses its
-- value column, and the only new table holds our own state per district (the
-- alert level and when it was first seen) so an alert needs the level to hold
-- for an hour before it is sent.
begin;
alter table public.cme_line_dust_sent drop column if exists value;

create table if not exists public.cme_dust_district_state (
  district text primary key check (char_length(district) between 1 and 40),
  level smallint not null check (level between 1 and 6),
  first_seen timestamptz not null default now(),
  checked_at timestamptz not null default now()
);
alter table public.cme_dust_district_state enable row level security;
revoke all on table public.cme_dust_district_state from anon, authenticated;
commit;
