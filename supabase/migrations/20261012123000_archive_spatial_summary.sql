begin;
create or replace function public.cme_archive_analytics(p_start timestamptz,p_end timestamptz,p_as_of timestamptz default null,p_forest text default null)
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
        order by observation_key,retrieved_at desc,id desc) revisions where p_forest is null or p_forest=any(revisions.forest_ids)
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
  ), coverage as materialized (
    select d.*,(lo<>day::timestamp at time zone 'Asia/Bangkok' or hi<>(day+1)::timestamp at time zone 'Asia/Bangkok') as partial_day,
      not exists(select 1 from (values('SNPP'),('NOAA-20'),('NOAA-21')) sensors(sensor)
        cross join lateral generate_series((d.lo at time zone 'UTC')::date,
          ((d.hi-interval '1 microsecond') at time zone 'UTC')::date,interval '1 day') u
        where not exists(select 1 from public.cme_firms_coverage c where c.sensor=sensors.sensor and c.utc_day=u::date
          and c.status='received' and c.retained_start<=d.lo and c.retained_end>=d.hi
          and c.checked_at>=least(d.hi,(u::date+1)::timestamp at time zone 'UTC')
          and (p_as_of is null or c.checked_at<=p_as_of))) as source_requests_complete
    from dates d
  ), daily as materialized (
    select c.day as date,c.partial_day,c.source_requests_complete,
      count(h.id) as observed_count,
      case when count(h.id)>0 or (c.source_requests_complete and not c.partial_day) then count(h.id) else null end as count
    from coverage c left join hs h on h.observed_at>=c.lo and h.observed_at<c.hi group by c.day,c.partial_day,c.source_requests_complete
  ), districts as (
    select coalesce(nullif(payload->'spatial_assignment'->>'district',''),nullif(payload->>'district',''),'ไม่ระบุ') as name,count(*) as count from hs group by 1
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
    select coalesce(nullif(payload->'spatial_assignment'->>'subdistrict',''),nullif(payload->>'subdistrict',''),nullif(payload->>'tambon','')) as name,count(*) as count from hs group by 1
  ), forests as (
    select f as forest_id,count(*) as count from hs cross join lateral unnest(forest_ids) f group by 1
  )
  select jsonb_build_object('start',p_start,'end',p_end,'as_of',p_as_of,
    'spatial_matched',(select count(*) from hs where payload->'spatial_assignment'->>'status'='matched'),'total',(select count(*) from hs),'hotspots',coalesce((select jsonb_agg(to_jsonb(d) order by d.date) from daily d),'[]'),
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
  if p_kind in ('all','hotspot') then
    result:=result||jsonb_build_object('hotspot_days',public.cme_archive_analytics(p_start,p_end,null,p_forest)->'hotspots');
  end if;
  return result;
end $$;
revoke all on function public.cme_archive_read(timestamptz,timestamptz,text,text,integer,integer) from public,anon,authenticated;
grant execute on function public.cme_archive_read(timestamptz,timestamptz,text,text,integer,integer) to service_role;
commit;
