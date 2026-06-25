create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  role text not null default 'resident'
    check (role in ('resident', 'community_reporter', 'committee', 'district_admin', 'system_admin')),
  community_id text,
  created_at timestamptz not null default now()
);

create table public.user_saved_locations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  label text not null,
  latitude double precision not null check (latitude between -90 and 90),
  longitude double precision not null check (longitude between -180 and 180),
  created_at timestamptz not null default now()
);

create table public.field_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  forest_id text not null,
  report_type text not null default 'weekly_activity'
    check (report_type in ('weekly_activity', 'smoke_observation', 'fire_observation', 'fuel_treatment')),
  patrol_count integer not null default 0 check (patrol_count >= 0),
  firebreak_km numeric not null default 0 check (firebreak_km >= 0),
  fuel_management_rai numeric not null default 0 check (fuel_management_rai >= 0),
  water_points_checked integer not null default 0 check (water_points_checked >= 0),
  committee_meeting boolean not null default false,
  community_use_activity boolean not null default false,
  no_burn_agreement boolean not null default false,
  latitude double precision check (latitude is null or latitude between -90 and 90),
  longitude double precision check (longitude is null or longitude between -180 and 180),
  note text not null default '',
  evidence_url text,
  verification_status text not null default 'pending'
    check (verification_status in ('pending', 'verified', 'rejected')),
  verified_by uuid references auth.users(id),
  verified_at timestamptz,
  submitted_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.user_saved_locations enable row level security;
alter table public.field_reports enable row level security;

grant select, insert on public.profiles to authenticated;
grant update (display_name, community_id) on public.profiles to authenticated;
grant select, insert, update, delete on public.user_saved_locations to authenticated;
grant select, insert, update on public.field_reports to authenticated;
grant select, insert, update, delete on public.profiles to service_role;
grant select, insert, update, delete on public.user_saved_locations to service_role;
grant select, insert, update, delete on public.field_reports to service_role;

create policy "Users can read own profile"
on public.profiles
for select
to authenticated
using ((select auth.uid()) = id);

create policy "Users can create own profile"
on public.profiles
for insert
to authenticated
with check ((select auth.uid()) = id);

create policy "Users can update own editable profile fields"
on public.profiles
for update
to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

create policy "Users can manage own saved locations"
on public.user_saved_locations
for all
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "Users can create own field reports"
on public.field_reports
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users can read own field reports"
on public.field_reports
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users can update own pending field reports"
on public.field_reports
for update
to authenticated
using ((select auth.uid()) = user_id and verification_status = 'pending')
with check ((select auth.uid()) = user_id and verification_status = 'pending');

create policy "District and system admins can read field reports"
on public.field_reports
for select
to authenticated
using (
  exists (
    select 1
    from public.profiles
    where profiles.id = (select auth.uid())
      and profiles.role in ('district_admin', 'system_admin')
  )
);

create policy "Committees can read their community reports"
on public.field_reports
for select
to authenticated
using (
  exists (
    select 1
    from public.profiles
    where profiles.id = (select auth.uid())
      and profiles.role = 'committee'
      and profiles.community_id = field_reports.forest_id
  )
);

create policy "District and system admins can verify field reports"
on public.field_reports
for update
to authenticated
using (
  exists (
    select 1
    from public.profiles
    where profiles.id = (select auth.uid())
      and profiles.role in ('district_admin', 'system_admin')
  )
)
with check (
  exists (
    select 1
    from public.profiles
    where profiles.id = (select auth.uid())
      and profiles.role in ('district_admin', 'system_admin')
  )
);
