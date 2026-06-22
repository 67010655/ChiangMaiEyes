-- ChiangMaiEyes — community field-report store (Supabase / Postgres + PostGIS)
-- Apply in the Supabase SQL editor (or `supabase db push`) before setting
-- SUPABASE_URL / SUPABASE_SERVICE_KEY. See memory: project-data-provenance.

create extension if not exists postgis;

create table if not exists field_activity_reports (
  id                      text primary key,
  forest_id               text        not null,
  village_id              text        not null,
  reporter_hash           text        not null,
  submitted_at            timestamptz not null default now(),
  patrol_count            integer     not null default 0,
  firebreak_km            real        not null default 0,
  fuel_management_rai     real        not null default 0,
  water_points_checked    integer     not null default 0,
  committee_meeting       boolean     not null default false,
  budget_used_baht        real        not null default 0,
  community_use_activity  boolean     not null default false,
  biodiversity_note       text        not null default '',
  no_burn_agreement       boolean     not null default false,
  created_at              timestamptz not null default now()
);

-- Defense-in-depth for the 1-report-per-forest/village/day rule (the API also
-- checks this): a DB-level unique index on the Bangkok calendar day.
create unique index if not exists field_reports_one_per_day
  on field_activity_reports (
    forest_id,
    village_id,
    ((submitted_at at time zone 'Asia/Bangkok')::date)
  );

create index if not exists field_reports_recent
  on field_activity_reports (submitted_at desc);

-- Row Level Security: writes go through the backend with the service-role key
-- (which bypasses RLS), so lock the table down to anon/auth clients. The public
-- league reads through the backend too, so no public policy is granted here.
alter table field_activity_reports enable row level security;
