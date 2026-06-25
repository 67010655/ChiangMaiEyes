# Auth And User Data Plan

## Recommendation

Recommended provider: Supabase.

Why:

- Auth and Postgres live in one product.
- Row Level Security supports user-owned rows and admin verification.
- The data model fits field reports, saved locations, committee review, and weekly ranking inputs.
- It can start as a thin backend integration without replacing the current FastAPI dashboard contract.

The frontend scaffold is already in place behind environment variables. Do not run the migration against production until the project owner chooses the real Supabase project and role ownership policy.

## Who This Serves

| User | Need |
|---|---|
| Resident | Save home or work location, check risk, submit simple smoke/fire observations |
| Community reporter | Submit patrol, firebreak, fuel-treatment, water-source, and no-burn agreement reports |
| Community forest committee | Review community reports and monitor weekly ranking evidence |
| District admin | Verify reports, correct community mapping, and coordinate response |
| System admin | Manage roles, data quality, and source integrations |

## Initial Roles

- `resident`
- `community_reporter`
- `committee`
- `district_admin`
- `system_admin`

## Initial Tables

```sql
create table profiles (
  id uuid primary key references auth.users(id),
  display_name text not null,
  role text not null default 'resident',
  community_id text,
  created_at timestamptz not null default now()
);

create table user_saved_locations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  label text not null,
  latitude double precision not null,
  longitude double precision not null,
  created_at timestamptz not null default now()
);

create table field_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  forest_id text not null,
  report_type text not null,
  patrol_count integer not null default 0,
  firebreak_km numeric not null default 0,
  fuel_management_rai numeric not null default 0,
  water_points_checked integer not null default 0,
  committee_meeting boolean not null default false,
  community_use_activity boolean not null default false,
  no_burn_agreement boolean not null default false,
  latitude double precision,
  longitude double precision,
  note text not null default '',
  evidence_url text,
  verification_status text not null default 'pending',
  verified_by uuid references auth.users(id),
  verified_at timestamptz,
  submitted_at timestamptz not null default now()
);
```

## Row Level Security Draft

```sql
alter table profiles enable row level security;
alter table user_saved_locations enable row level security;
alter table field_reports enable row level security;

create policy "Users can read own profile"
on profiles for select
using (auth.uid() = id);

create policy "Users can manage own saved locations"
on user_saved_locations for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "Users can create own field reports"
on field_reports for insert
with check (auth.uid() = user_id);

create policy "Users can read own field reports"
on field_reports for select
using (auth.uid() = user_id);
```

## Admin Review Policy Draft

```sql
create policy "District admins can read reports"
on field_reports for select
using (
  exists (
    select 1
    from profiles
    where profiles.id = auth.uid()
      and profiles.role in ('district_admin', 'system_admin')
  )
);
```

Backend service-role operations should be used only for trusted ranking aggregation, never from the browser.

The checked-in migration narrows profile updates with column grants so authenticated users can edit only `display_name` and `community_id`; `role` stays admin/service controlled.

## Product Rules

- A resident account should not be required just to view public risk and map data.
- Login becomes useful when saving locations, submitting field reports, or reviewing evidence.
- Weekly ranking should only use reports with clear provenance and a `verification_status`.
- User-submitted coordinates and notes must be treated as personal or sensitive until reviewed.
- Public UI should show aggregated scores, not raw reporter identity.

## First Auth Slice

1. Add Supabase project and environment variables.
2. Run the migration in `supabase/migrations/20260621065819_auth_user_reports.sql`.
3. Add profile bootstrap after signup.
4. Add saved locations for residents.
5. Add field report submission behind login.
6. Add district/committee review queue.
7. Feed verified reports into the weekly forest league.

Current scaffold status: the browser can request magic-link sign-in, save a selected community forest location, and submit a pending field report when `VITE_SUPABASE_URL` plus `VITE_SUPABASE_PUBLISHABLE_KEY` are set. Committee/admin review is represented in the migration policy layer, but the dedicated review UI and backend ranking aggregation job are still the next production slices.

## Environment Variables

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

Only the publishable browser key belongs in the frontend. The service-role key belongs only in backend/server environments.
