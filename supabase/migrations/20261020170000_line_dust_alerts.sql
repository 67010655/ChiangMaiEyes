-- Public dust alerts on LINE (no website account).
-- A person adds the Official Account and types "แจ้งเตือนฝุ่น <อำเภอ>"; we keep
-- only their LINE user id and the district. "หยุด" or blocking the account
-- deletes the row. Sends are recorded per person, day and PCD level so
-- nobody gets the same level twice in a day.
begin;
create table if not exists public.cme_line_dust_subs (
  line_user_id text primary key check (line_user_id ~ '^U[0-9a-f]{32}$'),
  district text not null check (char_length(district) between 1 and 40),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists cme_line_dust_subs_district on public.cme_line_dust_subs(district);

create table if not exists public.cme_line_dust_sent (
  line_user_id text not null check (line_user_id ~ '^U[0-9a-f]{32}$'),
  day date not null,
  level smallint not null check (level between 1 and 5),
  district text not null,
  value double precision,
  sent_at timestamptz not null default now(),
  primary key (line_user_id, day, level)
);

-- Service role only: no policies, no grants to anon/authenticated.
alter table public.cme_line_dust_subs enable row level security;
alter table public.cme_line_dust_sent enable row level security;
revoke all on table public.cme_line_dust_subs from anon, authenticated;
revoke all on table public.cme_line_dust_sent from anon, authenticated;
commit;
