begin;
-- Canonical exact detection key; unknown satellites stay provider-scoped.
-- Original rows/payloads are preserved, including SP/NRT revisions.
create function public.cme_detection_key(p_payload jsonb,p_source text,p_lat double precision,p_lon double precision,p_observed timestamptz)
returns text language plpgsql immutable set search_path='' as $$
declare satellite text; native text;
begin
  if p_lat is null or p_lon is null or p_observed is null then return null; end if;
  satellite:=regexp_replace(lower(coalesce(p_payload->>'satellite','')),'[^a-z0-9]','','g');
  satellite:=case satellite when 'n' then 'snpp' when 'suominpp' then 'snpp' when 'npp' then 'snpp'
    when 'n20' then 'noaa20' when 'jpss1' then 'noaa20' when 'n21' then 'noaa21' when 'jpss2' then 'noaa21'
    when 't' then 'terra' when 'a' then 'aqua' else satellite end;
  if satellite not in ('snpp','noaa20','noaa21','terra','aqua') then satellite:='source:'||lower(trim(p_source)); end if;
  native:='hotspot/v2|'||satellite||'|'||to_char(p_lat,'FM990.000000')||'|'||to_char(p_lon,'FM990.000000')||'|'||
    to_char(p_observed at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"');
  return encode(sha256(convert_to(native,'UTF8')),'hex');
end $$;
revoke all on function public.cme_detection_key(jsonb,text,double precision,double precision,timestamptz) from public,anon,authenticated;
grant execute on function public.cme_detection_key(jsonb,text,double precision,double precision,timestamptz) to service_role;

create table public.cme_archive_key_repairs(
  id text primary key references public.cme_observations(id), old_key text not null,new_key text not null,
  repaired_at timestamptz not null default now(),reason text not null default 'exact_detection_identity_v2'
);
alter table public.cme_archive_key_repairs enable row level security;
revoke all on public.cme_archive_key_repairs from public,anon,authenticated;
grant all on public.cme_archive_key_repairs to service_role;

insert into public.cme_archive_key_repairs(id,old_key,new_key)
select id,observation_key,public.cme_detection_key(payload,source,latitude,longitude,observed_at)
from public.cme_observations where kind='hotspot' and latitude is not null and longitude is not null
  and observation_key<>public.cme_detection_key(payload,source,latitude,longitude,observed_at);
update public.cme_observations o set observation_key=r.new_key from public.cme_archive_key_repairs r where o.id=r.id;

-- Enforce identity at ingestion too, including callers still running an old deployment.
create or replace function public.cme_archive_ingest(p_run jsonb,p_rows jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare n integer; inserted integer;
begin
  if jsonb_typeof(p_rows)<>'array' or jsonb_array_length(p_rows)>20000 or octet_length(p_rows::text)>16000000 then
    raise exception 'invalid archive batch' using errcode='22023'; end if;
  insert into public.cme_archive_runs(run_key,collected_at,mode,status,sources,counts)
  values(p_run->>'run_key',(p_run->>'collected_at')::timestamptz,p_run->>'mode',p_run->>'status',p_run->'sources',p_run->'counts')
  on conflict do nothing;
  get diagnostics n=row_count;
  if n=0 then return jsonb_build_object('already_collected',true,'inserted',0); end if;
  insert into public.cme_observations
  select x.id,case when x.kind='hotspot' then coalesce(public.cme_detection_key(x.payload,x.source,x.latitude,x.longitude,x.observed_at),x.observation_key) else x.observation_key end,
    x.kind,x.observed_at,x.retrieved_at,x.source,x.latitude,x.longitude,x.forest_ids,x.payload
  from jsonb_to_recordset(p_rows) as x(id text,observation_key text,kind text,observed_at timestamptz,retrieved_at timestamptz,source text,latitude double precision,longitude double precision,forest_ids text[],payload jsonb)
  on conflict do nothing;
  get diagnostics inserted=row_count;
  return jsonb_build_object('already_collected',false,'inserted',inserted);
end $$;
revoke all on function public.cme_archive_ingest(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.cme_archive_ingest(jsonb,jsonb) to service_role;

create or replace function public.cme_archive_read(p_start timestamptz,p_end timestamptz,p_kind text,p_forest text default null,p_offset integer default 0,p_limit integer default 500) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare result jsonb;
begin
  if p_end<=p_start or p_end-p_start>interval '367 days' or p_kind not in ('all','hotspot','pm25','weather') or p_offset<0 or p_offset>1000000 or p_limit<1 or p_limit>1000 then raise exception 'invalid archive window' using errcode='22023'; end if;
  with obs as (
    select distinct on(observation_key) * from public.cme_observations
    where observed_at>=p_start and observed_at<p_end and (p_kind='all' or kind=p_kind)
      and (p_forest is null or p_forest=any(forest_ids))
      and (kind<>'pm25' or payload->>'measurement_kind'='measured' or payload->>'id' like 'CM-%')
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
    'legacy_pm25_excluded',(select count(*) from public.cme_observations where kind='pm25' and observed_at>=p_start and observed_at<p_end
      and (p_forest is null or p_forest=any(forest_ids))
      and not(coalesce(payload->>'measurement_kind','')='measured' or coalesce(payload->>'id','') like 'CM-%')),
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
