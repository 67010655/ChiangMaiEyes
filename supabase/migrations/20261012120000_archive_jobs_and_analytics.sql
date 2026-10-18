begin;

-- A small index of the latest received revision. Original evidence remains append-only.
create table public.cme_observation_heads (
  observation_key text primary key, id text not null references public.cme_observations(id),
  kind text not null, observed_at timestamptz not null, retrieved_at timestamptz not null
);
create index cme_heads_window on public.cme_observation_heads(kind,observed_at);
alter table public.cme_observation_heads enable row level security;
revoke all on public.cme_observation_heads from public,anon,authenticated;
grant all on public.cme_observation_heads to service_role;
insert into public.cme_observation_heads
select distinct on(observation_key) observation_key,id,kind,observed_at,retrieved_at
from public.cme_observations order by observation_key,retrieved_at desc,id desc;
create function public.cme_advance_observation_head() returns trigger
language plpgsql security definer set search_path='' as $$
begin
  insert into public.cme_observation_heads values(new.observation_key,new.id,new.kind,new.observed_at,new.retrieved_at)
  on conflict(observation_key) do update set id=excluded.id,kind=excluded.kind,
    observed_at=excluded.observed_at,retrieved_at=excluded.retrieved_at
  where (excluded.retrieved_at,excluded.id)>(cme_observation_heads.retrieved_at,cme_observation_heads.id);
  return new;
end $$;
revoke all on function public.cme_advance_observation_head() from public,anon,authenticated;
create trigger cme_observation_head_insert after insert on public.cme_observations
for each row execute function public.cme_advance_observation_head();

-- Coverage means a source request returned a valid CSV, not that every fire was detected.
create table public.cme_firms_coverage (
  run_key text not null, sensor text not null check(sensor in ('SNPP','NOAA-20','NOAA-21')),
  utc_day date not null, source text not null,
  status text not null check(status in ('received','partial','unavailable','not_available')),
  checked_at timestamptz not null, invalid_rows integer not null default 0,
  retained_start timestamptz,retained_end timestamptz,
  primary key(run_key,sensor,utc_day)
);
create index cme_coverage_day on public.cme_firms_coverage(utc_day,sensor,checked_at desc);
alter table public.cme_firms_coverage enable row level security;
revoke all on public.cme_firms_coverage from public,anon,authenticated;
grant all on public.cme_firms_coverage to service_role;
insert into public.cme_firms_coverage(run_key,sensor,utc_day,source,status,checked_at,invalid_rows)
select r.run_key,c->>'sensor',(c->>'utc_start')::date+g.i,c->>'source',c->>'status',r.collected_at,
       coalesce((c->>'invalid_rows')::integer,0)
from public.cme_archive_runs r
cross join lateral jsonb_array_elements(case when jsonb_typeof(r.sources)='array' then r.sources else '[]' end) c
cross join lateral generate_series(0,least(5,greatest(0,coalesce((c->>'days')::integer,0)))-1) g(i)
where c->>'sensor' in ('SNPP','NOAA-20','NOAA-21') and c->>'utc_start' ~ '^\d{4}-\d{2}-\d{2}$'
  and c->>'status' in ('received','partial','unavailable','not_available')
on conflict do nothing;

create table public.cme_archive_jobs (
  id uuid primary key, request_key text not null unique,
  start_at timestamptz not null,end_at timestamptz not null,
  requested_at timestamptz not null default now(),requested_by uuid,
  include_models boolean not null default true,
  status text not null default 'queued' check(status in ('queued','running','completed','partial','failed')),
  check(end_at>start_at and end_at-start_at<=interval '367 days')
);
create table public.cme_archive_tasks (
  id bigint generated always as identity primary key,
  job_id uuid not null references public.cme_archive_jobs(id),task_key text not null,
  kind text not null check(kind in ('firms_plan','firms','pm25_model','weather_model')),
  payload jsonb not null, status text not null default 'queued'
    check(status in ('queued','running','received','partial','not_available','failed')),
  attempts integer not null default 0,available_at timestamptz not null default now(),
  lease_until timestamptz,lease_token uuid,
  received integer not null default 0,result jsonb not null default '{}',
  attempt_log jsonb not null default '[]',finished_at timestamptz,
  unique(job_id,task_key), check(octet_length(payload::text)<=4000)
);
create index cme_task_queue on public.cme_archive_tasks(available_at,id) where status in ('queued','running');
alter table public.cme_archive_jobs enable row level security;
alter table public.cme_archive_tasks enable row level security;
revoke all on public.cme_archive_jobs,public.cme_archive_tasks from public,anon,authenticated;
grant all on public.cme_archive_jobs,public.cme_archive_tasks to service_role;
grant usage,select on sequence public.cme_archive_tasks_id_seq to service_role;

create function public.cme_archive_enqueue(p_job jsonb,p_tasks jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare j public.cme_archive_jobs%rowtype;
begin
  if jsonb_typeof(p_tasks)<>'array' or jsonb_array_length(p_tasks)>200 then raise exception 'invalid tasks' using errcode='22023'; end if;
  insert into public.cme_archive_jobs(id,request_key,start_at,end_at,requested_by,include_models)
  values((p_job->>'id')::uuid,p_job->>'request_key',(p_job->>'start_at')::timestamptz,
    (p_job->>'end_at')::timestamptz,(p_job->>'requested_by')::uuid,coalesce((p_job->>'include_models')::boolean,true))
  on conflict(request_key) do nothing;
  select * into j from public.cme_archive_jobs where request_key=p_job->>'request_key';
  insert into public.cme_archive_tasks(job_id,task_key,kind,payload)
  select j.id,x.task_key,x.kind,x.payload from jsonb_to_recordset(p_tasks) x(task_key text,kind text,payload jsonb)
  on conflict do nothing;
  return to_jsonb(j);
end $$;
revoke all on function public.cme_archive_enqueue(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.cme_archive_enqueue(jsonb,jsonb) to service_role;

create function public.cme_archive_claim(p_token uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.cme_archive_tasks%rowtype;
begin
  -- Every caller shares this lock. Public triggers cannot create jobs, select
  -- arbitrary URLs, or run more than two upstream requests concurrently.
  perform pg_advisory_xact_lock(12102026);
  update public.cme_archive_tasks set status='failed',lease_until=null,lease_token=null,
    result=result||'{"error":"lease_expired"}'::jsonb,finished_at=now(),
    attempt_log=attempt_log||jsonb_build_array(jsonb_build_object('at',now(),'event','lease_expired'))
  where status='running' and lease_until<now() and attempts>=3;
  update public.cme_archive_jobs j set status=case
    when not exists(select 1 from public.cme_archive_tasks q where q.job_id=j.id and q.status in ('failed','partial','not_available')) then 'completed'
    when exists(select 1 from public.cme_archive_tasks q where q.job_id=j.id and q.status in ('received','partial')) then 'partial' else 'failed' end
  where j.status in ('queued','running') and exists(select 1 from public.cme_archive_tasks q where q.job_id=j.id)
    and not exists(select 1 from public.cme_archive_tasks q where q.job_id=j.id and q.status in ('queued','running'));
  if (select count(*) from public.cme_archive_tasks where status='running' and lease_until>now())>=2 then return null; end if;
  select * into t from public.cme_archive_tasks
  where (status='queued' and available_at<=now()) or (status='running' and lease_until<now() and attempts<3)
  order by available_at,id for update skip locked limit 1;
  if not found then return null; end if;
  update public.cme_archive_tasks set status='running',attempts=attempts+1,
    lease_until=now()+interval '90 seconds',lease_token=p_token,
    attempt_log=attempt_log||jsonb_build_array(jsonb_build_object('at',now(),'attempt',attempts+1,'event','claimed'))
  where id=t.id returning * into t;
  update public.cme_archive_jobs set status='running' where id=t.job_id;
  return to_jsonb(t)||(select jsonb_build_object('start_at',start_at,'end_at',end_at,'include_models',include_models)
    from public.cme_archive_jobs where id=t.job_id);
end $$;
revoke all on function public.cme_archive_claim(uuid) from public,anon,authenticated;
grant execute on function public.cme_archive_claim(uuid) to service_role;

create function public.cme_archive_finish(p_id bigint,p_token uuid,p_result jsonb,p_rows jsonb,p_children jsonb default '[]') returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.cme_archive_tasks%rowtype; state text; run jsonb; saved jsonb; pending integer; failures integer; received_tasks integer;
begin
  select * into t from public.cme_archive_tasks where id=p_id for update;
  if not found or t.status<>'running' or t.lease_token<>p_token or t.lease_until<now() then
    raise exception 'worker lease lost' using errcode='40001'; end if;
  state:=p_result->>'status';
  if state is null or state not in ('received','partial','not_available','unavailable') or p_rows is null or jsonb_typeof(p_rows)<>'array'
    or jsonb_typeof(p_children)<>'array' or jsonb_array_length(p_children)>400 then raise exception 'invalid task result' using errcode='22023'; end if;
  if state='unavailable' then
    update public.cme_archive_tasks set status=case when attempts>=3 then 'failed' else 'queued' end,
      available_at=now()+make_interval(secs=>least(300,15*(2^attempts)::integer)),
      lease_until=null,lease_token=null,result=p_result,
      attempt_log=attempt_log||jsonb_build_array(jsonb_build_object('at',now(),'event','upstream_failed','code',p_result->>'error'))
    where id=p_id;
  else
    run:=jsonb_build_object('run_key','task/'||t.id||'/'||t.attempts,'collected_at',now(),'mode','backfill',
      'status',case when state='received' then 'complete' else 'partial' end,'sources',jsonb_build_array(p_result),'counts',jsonb_build_object(t.kind,jsonb_array_length(p_rows)));
    saved:=public.cme_archive_ingest(run,p_rows);
    insert into public.cme_archive_tasks(job_id,task_key,kind,payload,status,result,finished_at)
    select t.job_id,x.task_key,x.kind,x.payload,coalesce(x.status,'queued'),coalesce(x.result,'{}'),
      case when x.status='not_available' then now() else null end
    from jsonb_to_recordset(p_children) x(task_key text,kind text,payload jsonb,status text,result jsonb)
    on conflict do nothing;
    if t.kind='firms' and p_result->>'sensor' in ('SNPP','NOAA-20','NOAA-21') then
      insert into public.cme_firms_coverage(run_key,sensor,utc_day,source,status,checked_at,invalid_rows,retained_start,retained_end)
      select run->>'run_key',p_result->>'sensor',(p_result->>'utc_start')::date+g.i,
        p_result->>'source',state,now(),coalesce((p_result->>'invalid_rows')::integer,0),j.start_at,j.end_at
      from generate_series(0,(p_result->>'days')::integer-1) g(i),public.cme_archive_jobs j where j.id=t.job_id on conflict do nothing;
    end if;
    update public.cme_archive_tasks set status=state,lease_until=null,lease_token=null,
      received=jsonb_array_length(p_rows),result=p_result,finished_at=now(),
      attempt_log=attempt_log||jsonb_build_array(jsonb_build_object('at',now(),'event',state,'received',jsonb_array_length(p_rows))) where id=p_id;
  end if;
  select count(*) filter(where status in ('queued','running')),
    count(*) filter(where status in ('failed','partial','not_available')),
    count(*) filter(where status in ('received','partial')) into pending,failures,received_tasks
  from public.cme_archive_tasks where job_id=t.job_id;
  update public.cme_archive_jobs set status=case when pending>0 then 'running'
    when failures=0 then 'completed' when received_tasks>0 then 'partial' else 'failed' end where id=t.job_id;
  return jsonb_build_object('saved',saved,'pending',pending);
end $$;
revoke all on function public.cme_archive_finish(bigint,uuid,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.cme_archive_finish(bigint,uuid,jsonb,jsonb,jsonb) to service_role;

create function public.cme_archive_retry(p_job uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare n integer;
begin
  update public.cme_archive_tasks set status='queued',available_at=now(),attempts=0,
    lease_until=null,lease_token=null,finished_at=null where job_id=p_job and status='failed';
  get diagnostics n=row_count;
  if n>0 then update public.cme_archive_jobs set status='queued' where id=p_job; end if;
  return jsonb_build_object('retried',n);
end $$;
revoke all on function public.cme_archive_retry(uuid) from public,anon,authenticated;
grant execute on function public.cme_archive_retry(uuid) to service_role;

create function public.cme_archive_job_status(p_job uuid default null) returns jsonb
language sql stable security definer set search_path='' as $$
select coalesce(jsonb_agg(to_jsonb(q) order by q.requested_at desc),'[]') from (
  select j.id,j.start_at,j.end_at,j.requested_at,j.status,j.include_models,
    count(t.id) as tasks,count(t.id) filter(where t.status in ('received','partial','not_available','failed')) as finished,
    count(t.id) filter(where t.status='failed') as failed,count(t.id) filter(where t.status='not_available') as not_available,
    coalesce(sum(t.received),0) as received,
    coalesce(jsonb_agg(jsonb_build_object('id',t.id,'kind',t.kind,'status',t.status,'attempts',t.attempts,
      'received',t.received,'result',t.result,'attempt_log',t.attempt_log) order by t.id) filter(where t.id is not null),'[]') as detail
  from public.cme_archive_jobs j left join public.cme_archive_tasks t on t.job_id=j.id
  where p_job is null or j.id=p_job group by j.id order by j.requested_at desc limit 8
) q;
$$;
revoke all on function public.cme_archive_job_status(uuid) from public,anon,authenticated;
grant execute on function public.cme_archive_job_status(uuid) to service_role;

-- A fast current view and an explicit as-of replay share the exact same window.
create function public.cme_archive_analytics(p_start timestamptz,p_end timestamptz,p_as_of timestamptz default null,p_forest text default null)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare result jsonb;
begin
  if p_end<=p_start or p_end-p_start>interval '367 days' then raise exception 'invalid history window' using errcode='22023'; end if;
  with obs as materialized (
    select o.* from public.cme_observation_heads h join public.cme_observations o on o.id=h.id
    where p_as_of is null and h.observed_at>=p_start and h.observed_at<p_end and (p_forest is null or p_forest=any(o.forest_ids))
    union all
    select * from (select distinct on(observation_key) * from public.cme_observations
      where p_as_of is not null and observed_at>=p_start and observed_at<p_end and retrieved_at<=p_as_of
        and (p_forest is null or p_forest=any(forest_ids)) order by observation_key,retrieved_at desc,id desc) revisions
  ), hs as materialized (
    select *,case when payload->>'confidence_level' in ('low','nominal','high') then payload->>'confidence_level'
      when (source like 'VIIRS_%' or source='NASA FIRMS') and lower(payload->>'confidence') in ('l','n','h') then
        case lower(payload->>'confidence') when 'l' then 'low' when 'n' then 'nominal' else 'high' end else 'unknown' end as native_level
    from obs where kind='hotspot'
  ), pm as materialized (
    select * from obs where kind='pm25' and (payload->>'measurement_kind' in ('measured','model') or payload->>'id' like 'CM-%')
  ), dates as (
    select d::date as day,greatest(p_start,d::date::timestamp at time zone 'Asia/Bangkok') as lo,
      least(p_end,(d::date+1)::timestamp at time zone 'Asia/Bangkok') as hi
    from generate_series((p_start at time zone 'Asia/Bangkok')::date,
      ((p_end-interval '1 microsecond') at time zone 'Asia/Bangkok')::date,interval '1 day') d
  ), coverage as (
    select d.*,(lo<>day::timestamp at time zone 'Asia/Bangkok' or hi<>(day+1)::timestamp at time zone 'Asia/Bangkok') as partial_day,
      not exists(select 1 from (values('SNPP'),('NOAA-20'),('NOAA-21')) sensors(sensor)
        cross join lateral generate_series((d.lo at time zone 'UTC')::date,
          ((d.hi-interval '1 microsecond') at time zone 'UTC')::date,interval '1 day') u
        where not exists(select 1 from public.cme_firms_coverage c where c.sensor=sensors.sensor and c.utc_day=u::date
          and c.status='received' and c.retained_start<=d.lo and c.retained_end>=d.hi
          and c.checked_at>=least(d.hi,(u::date+1)::timestamp at time zone 'UTC')
          and (p_as_of is null or c.checked_at<=p_as_of))) as source_requests_complete
    from dates d
  ), daily as (
    select c.day as date,c.partial_day,c.source_requests_complete,
      count(h.id) as observed_count,
      case when count(h.id)>0 or (c.source_requests_complete and not c.partial_day) then count(h.id) else null end as count
    from coverage c left join hs h on h.observed_at>=c.lo and h.observed_at<c.hi group by c.day,c.partial_day,c.source_requests_complete
  ), districts as (
    select coalesce(nullif(payload->>'district',''),'ไม่ระบุ') as name,count(*) as count from hs group by 1
  ), hourly as (
    select extract(hour from observed_at at time zone 'Asia/Bangkok')::int as hour,count(*) as count from hs group by 1
  ), pm_days as (
    select (observed_at at time zone 'Asia/Bangkok')::date as date,
      case when payload->>'measurement_kind'='model' then 'model' else 'measured' end as measurement_kind,
      avg((payload->>'pm25')::double precision) as value,count(*) as samples,
      count(distinct payload->>'id') as stations from pm group by 1,2
  ), weather_days as (
    select (observed_at at time zone 'Asia/Bangkok')::date as date,
      case when payload->>'measurement_kind'='model' or source like 'Open-Meteo%' then 'model' else 'station' end as measurement_kind,
      max((payload->>'temperature_c')::double precision) as temp_max,min((payload->>'temperature_c')::double precision) as temp_min,
      max((payload->>'wind_speed_kmh')::double precision) as wind_max,avg((payload->>'humidity_percent')::double precision) as humidity,
      count(*) as samples,source from obs where kind='weather' group by 1,2,source
  ), source_rows as (
    select source,count(distinct observation_key) as count from public.cme_observations where kind='hotspot'
      and observed_at>=p_start and observed_at<p_end and (p_as_of is null or retrieved_at<=p_as_of)
      and (p_forest is null or p_forest=any(forest_ids)) group by source
  ), tambons as (
    select coalesce(nullif(payload->>'subdistrict',''),nullif(payload->>'tambon','')) as name,count(*) as count from hs group by 1
  ), forests as (
    select f as forest_id,count(*) as count from hs cross join lateral unnest(forest_ids) f group by 1
  )
  select jsonb_build_object('start',p_start,'end',p_end,'as_of',p_as_of,
    'total',(select count(*) from hs),'hotspots',coalesce((select jsonb_agg(to_jsonb(d) order by d.date) from daily d),'[]'),
    'districts',coalesce((select jsonb_agg(to_jsonb(d) order by d.count desc,d.name) from districts d),'[]'),
    'hour_histogram',(select jsonb_agg(coalesce(h.count,0) order by hours.hour) from generate_series(0,23) hours(hour) left join hourly h using(hour)),
    'satellites',(select coalesce(jsonb_agg(to_jsonb(s)), '[]') from (select coalesce(payload->>'satellite','ไม่ระบุ') name,count(*) count from hs group by 1) s),
    'confidence',(select jsonb_object_agg(native_level,n) from(select native_level,count(*) n from hs group by 1)c),
    'frp',jsonb_build_object('known',(select count(*) from hs where payload->>'frp' is not null),
      'max',(select max((payload->>'frp')::double precision) from hs),'mean',(select avg((payload->>'frp')::double precision) from hs),
      'bins',(select jsonb_agg(n order by b) from(select bins.b,count(h.id) n from generate_series(0,6) bins(b)
        left join hs h on least(6,floor((h.payload->>'frp')::double precision/20)::int)=bins.b group by bins.b) z)),
    'pm25',coalesce((select jsonb_agg(to_jsonb(p) order by p.date,p.measurement_kind) from pm_days p),'[]'),
    'weather',coalesce((select jsonb_agg(to_jsonb(w) order by w.date,w.measurement_kind) from weather_days w),'[]'),
    'sources',coalesce((select jsonb_agg(to_jsonb(s) order by s.source) from source_rows s),'[]'),
    'tambons',coalesce((select jsonb_agg(to_jsonb(t) order by t.count desc) from tambons t where t.name is not null),'[]'),
    'forests',coalesce((select jsonb_agg(to_jsonb(f) order by f.count desc) from forests f),'[]'),
    'coverage_complete',(select bool_and(source_requests_complete) from coverage),
    'days_with_observations',(select count(*) from daily where observed_count>0),
    'last_received',(select max(retrieved_at) from obs),'checked_at',now()) into result;
  return result;
end $$;
revoke all on function public.cme_archive_analytics(timestamptz,timestamptz,timestamptz,text) from public,anon,authenticated;
grant execute on function public.cme_archive_analytics(timestamptz,timestamptz,timestamptz,text) to service_role;
create or replace function public.cme_archive_read(p_start timestamptz,p_end timestamptz,p_kind text,p_forest text default null,p_offset integer default 0,p_limit integer default 500) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare result jsonb;
begin
  if p_end<=p_start or p_end-p_start>interval '367 days' or p_kind not in ('all','hotspot','pm25','pm25_model','weather') or p_offset<0 or p_offset>1000000 or p_limit<1 or p_limit>1000 then raise exception 'invalid archive window' using errcode='22023'; end if;
  with obs as (
    select o.* from public.cme_observation_heads h join public.cme_observations o on o.id=h.id
    where h.observed_at>=p_start and h.observed_at<p_end
      and (p_kind='all' or h.kind=p_kind or (p_kind='pm25_model' and h.kind='pm25'))
      and (p_forest is null or p_forest=any(o.forest_ids))
      and (h.kind<>'pm25' or payload->>'measurement_kind' in ('measured','model') or payload->>'id' like 'CM-%')
      and (p_kind<>'pm25' or coalesce(payload->>'measurement_kind','measured')='measured')
      and (p_kind<>'pm25_model' or payload->>'measurement_kind'='model')
  ), daily as (
    select (observed_at at time zone 'Asia/Bangkok')::date as day,kind,source,coalesce(payload->>'measurement_kind',case when kind='weather' and source like 'Open-Meteo%' then 'model' else 'measured' end) as measurement_kind,count(*) as samples,
      case when kind='pm25' then avg((payload->>'pm25')::double precision) else null end as pm25_mean,
      case when kind='weather' then avg((payload->>'wind_speed_kmh')::double precision) else null end as wind_mean_kmh
    from obs group by 1,2,3,4
  )
  select jsonb_build_object('total',(select count(*) from obs),
    'rows',coalesce((select jsonb_agg(to_jsonb(q)) from(select * from obs order by observed_at desc,id offset p_offset limit p_limit) q),'[]'),
    'daily',coalesce((select jsonb_agg(to_jsonb(d) order by d.day,d.kind,d.source) from daily d),'[]'),
    'legacy_pm25_excluded',(select count(*) from public.cme_observations where kind='pm25' and observed_at>=p_start and observed_at<p_end
      and (p_forest is null or p_forest=any(forest_ids))
      and not(coalesce(payload->>'measurement_kind','')in ('measured','model') or coalesce(payload->>'id','') like 'CM-%')),
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
commit;
