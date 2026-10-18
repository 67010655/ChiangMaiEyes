begin;
-- Public upstream environmental observations. No community incident, user,
-- email, or private-photo payload is stored in these tables.
create table public.cme_archive_runs (
  run_key text primary key, collected_at timestamptz not null,
  mode text not null check(mode in ('scheduled','backfill')),
  status text not null check(status in ('complete','partial','unavailable')),
  sources jsonb not null, counts jsonb not null,
  created_at timestamptz not null default now()
);
create table public.cme_observations (
  id text primary key, observation_key text not null,
  kind text not null check(kind in ('hotspot','pm25','weather')),
  observed_at timestamptz not null, retrieved_at timestamptz not null,
  source text not null, latitude double precision, longitude double precision,
  forest_ids text[] not null default '{}', payload jsonb not null,
  check(octet_length(payload::text)<=16000),
  check((latitude is null)=(longitude is null)),
  check(latitude between -90 and 90 and longitude between -180 and 180)
);
create index cme_obs_time on public.cme_observations(kind,observed_at desc);
create index cme_obs_key on public.cme_observations(observation_key,retrieved_at desc);
create index cme_obs_forests on public.cme_observations using gin(forest_ids);
alter table public.cme_archive_runs enable row level security;
alter table public.cme_observations enable row level security;
revoke all on public.cme_archive_runs,public.cme_observations from public,anon,authenticated;
grant all on public.cme_archive_runs,public.cme_observations to service_role;
create function public.cme_archive_ingest(p_run jsonb,p_rows jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare n integer; inserted integer;
begin
  if jsonb_typeof(p_rows)<>'array' or jsonb_array_length(p_rows)>20000 or
     octet_length(p_rows::text)>16000000 then raise exception 'invalid archive batch' using errcode='22023'; end if;
  insert into public.cme_archive_runs(run_key,collected_at,mode,status,sources,counts)
  values(p_run->>'run_key',(p_run->>'collected_at')::timestamptz,p_run->>'mode',p_run->>'status',p_run->'sources',p_run->'counts')
  on conflict do nothing;
  get diagnostics n=row_count;
  if n=0 then return jsonb_build_object('already_collected',true,'inserted',0); end if;
  insert into public.cme_observations
  select x.id,x.observation_key,x.kind,x.observed_at,x.retrieved_at,x.source,x.latitude,x.longitude,x.forest_ids,x.payload
  from jsonb_to_recordset(p_rows) as x(id text,observation_key text,kind text,observed_at timestamptz,retrieved_at timestamptz,source text,latitude double precision,longitude double precision,forest_ids text[],payload jsonb)
  on conflict do nothing;
  get diagnostics inserted=row_count;
  return jsonb_build_object('already_collected',false,'inserted',inserted);
end $$;
revoke all on function public.cme_archive_ingest(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.cme_archive_ingest(jsonb,jsonb) to service_role;

create function public.cme_archive_read(p_start timestamptz,p_end timestamptz,p_kind text,p_forest text default null,p_offset integer default 0,p_limit integer default 500) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare result jsonb;
begin
  if p_end<=p_start or p_end-p_start>interval '367 days' or p_kind not in ('all','hotspot','pm25','weather') or p_offset<0 or p_offset>1000000 or p_limit<1 or p_limit>1000 then raise exception 'invalid archive window' using errcode='22023'; end if;
  with obs as (
    select distinct on(observation_key) * from public.cme_observations
    where observed_at>=p_start and observed_at<p_end and (p_kind='all' or kind=p_kind)
      and (p_forest is null or p_forest=any(forest_ids))
    order by observation_key,retrieved_at desc,id desc
  ), daily as (
    select (observed_at at time zone 'Asia/Bangkok')::date as day,kind,source,count(*) as samples,
      case when kind='pm25' then avg((payload->>'pm25')::double precision) else null end as pm25_mean,
      case when kind='weather' then avg((payload->>'wind_speed_kmh')::double precision) else null end as wind_mean_kmh
    from obs group by 1,2,3
  )
  select jsonb_build_object('total',(select count(*) from obs),
    'rows',coalesce((select jsonb_agg(to_jsonb(q)) from(select * from obs order by observed_at desc,id offset p_offset limit p_limit) q),'[]'),
    'daily',coalesce((select jsonb_agg(to_jsonb(d) order by d.day,d.kind,d.source) from daily d),'[]'),
    'collection',coalesce((select jsonb_agg(to_jsonb(g) order by g.day) from(
      select (collected_at at time zone 'Asia/Bangkok')::date as day,count(*) as checks,
      count(*) filter(where status='complete') as complete_checks,
      count(*) filter(where status='partial') as partial_checks,
      count(*) filter(where status='unavailable') as failed_checks
      from public.cme_archive_runs where mode='scheduled' and collected_at>=p_start and collected_at<p_end group by 1) g),'[]'),
    'first_collected',(select min(collected_at) from public.cme_archive_runs),
    'last_collected',(select max(collected_at) from public.cme_archive_runs),
    'recent_runs',coalesce((select jsonb_agg(to_jsonb(g)) from(select * from public.cme_archive_runs order by collected_at desc limit 8)g),'[]')) into result;
  return result;
end $$;
revoke all on function public.cme_archive_read(timestamptz,timestamptz,text,text,integer,integer) from public,anon,authenticated;
grant execute on function public.cme_archive_read(timestamptz,timestamptz,text,text,integer,integer) to service_role;

-- Private, append-only field/research evidence. Corrections preserve originals.
create table public.cme_research_records (
  id uuid primary key, forest_id text not null references public.cme_forests(forest_id),
  kind text not null check(kind in ('fuel','pilot','model','burned_area')),
  recorded_by uuid not null references auth.users(id), data jsonb not null,
  corrects_id uuid references public.cme_research_records(id),
  created_at timestamptz not null default now(),
  check(octet_length(data::text)<=400000)
);
create index cme_research_forest on public.cme_research_records(forest_id,kind,created_at desc);
alter table public.cme_research_records enable row level security;
revoke all on public.cme_research_records from public,anon,authenticated;
grant select on public.cme_research_records to authenticated;
grant all on public.cme_research_records to service_role;
create policy cme_research_read on public.cme_research_records for select to authenticated
  using(public.cme_is_admin() or public.cme_is_member(forest_id));
create function public.cme_research_save(p_id uuid,p_forest text,p_kind text,p_data jsonb,p_corrects uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare r public.cme_research_records%rowtype;
begin
  if not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) or
    not(public.cme_is_admin() or public.cme_is_member(p_forest)) then raise exception 'ไม่มีสิทธิ์บันทึกในป่านี้' using errcode='42501'; end if;
  if p_kind not in ('fuel','pilot','model','burned_area') or jsonb_typeof(p_data)<>'object' or octet_length(p_data::text)>400000 then raise exception 'รูปแบบหลักฐานไม่ถูกต้อง' using errcode='22023'; end if;
  perform pg_advisory_xact_lock(hashtext(p_id::text));
  select * into r from public.cme_research_records where id=p_id;
  if found then
    if r.recorded_by<>auth.uid() or r.forest_id<>p_forest or r.kind<>p_kind or r.data<>p_data or r.corrects_id is distinct from p_corrects then raise exception 'รหัสนี้ถูกใช้กับข้อมูลอื่นแล้ว' using errcode='23505'; end if;
    return to_jsonb(r);
  end if;
  if p_corrects is not null and not exists(select 1 from public.cme_research_records where id=p_corrects and forest_id=p_forest and kind=p_kind) then raise exception 'แก้ได้เฉพาะหลักฐานชนิดเดียวกันในป่าเดียวกัน' using errcode='22023'; end if;
  insert into public.cme_research_records(id,forest_id,kind,recorded_by,data,corrects_id)
  values(p_id,p_forest,p_kind,auth.uid(),p_data,p_corrects) returning * into r;
  return to_jsonb(r);
end $$;
revoke all on function public.cme_research_save(uuid,text,text,jsonb,uuid) from public,anon,authenticated;
grant execute on function public.cme_research_save(uuid,text,text,jsonb,uuid) to authenticated;
commit;
