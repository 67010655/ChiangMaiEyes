-- The one-year view still came close to PostgREST's 8 s limit (5.5–8.8 s): every summary scanned the full
-- observation rows again (about 15 passes over 33,000 rows with their jsonb payload, 0.2–0.4 s each).
-- Each needed field is now read from the payload once, in the obs step; the summaries use those small columns.
-- Same signature, grants and results as 20261024090000_archive_analytics_daily_by_date.
begin;

create or replace function public.cme_archive_analytics(p_start timestamptz,p_end timestamptz,p_as_of timestamptz default null,p_forest text default null,p_district text default null)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare result jsonb;
begin
  if p_end<=p_start or p_end-p_start>interval '367 days' then raise exception 'invalid history window' using errcode='22023'; end if;
  with raw as (
    select o.id,o.kind,o.observed_at,o.retrieved_at,o.source,o.forest_ids,o.payload from public.cme_observation_heads h join public.cme_observations o on o.id=h.id
    where p_as_of is null and h.observed_at>=p_start and h.observed_at<p_end and (p_forest is null or p_forest=any(o.forest_ids))
    union all
    select id,kind,observed_at,retrieved_at,source,forest_ids,payload from (select distinct on(observation_key) * from public.cme_observations
      where p_as_of is not null and observed_at>=p_start and observed_at<p_end and retrieved_at<=p_as_of
        order by observation_key,retrieved_at desc,id desc) revisions where p_forest is null or p_forest=any(revisions.forest_ids)
  ), obs as materialized (
    select id,kind,observed_at,retrieved_at,source,forest_ids,
      coalesce(nullif(payload->'spatial_assignment'->>'district',''),nullif(payload->>'district',''),'ไม่ระบุ') as district,
      coalesce(nullif(payload->'spatial_assignment'->>'subdistrict',''),nullif(payload->>'subdistrict',''),nullif(payload->>'tambon','')) as subdistrict,
      payload->'spatial_assignment'->>'status' as sa_status,
      payload->>'satellite' as satellite,
      (payload->>'frp')::double precision as frp,
      case when payload->>'confidence_level' in ('low','nominal','high') then payload->>'confidence_level'
        when (source like 'VIIRS_%' or source='NASA FIRMS') and lower(payload->>'confidence') in ('l','n','h') then
          case lower(payload->>'confidence') when 'l' then 'low' when 'n' then 'nominal' else 'high' end else 'unknown' end as native_level,
      payload->>'measurement_kind' as measurement_kind,
      payload->>'id' as pid,
      case when kind='pm25' then (payload->>'pm25')::double precision end as pm25,
      case when kind='weather' then (payload->>'temperature_c')::double precision end as temperature_c,
      case when kind='weather' then (payload->>'wind_speed_kmh')::double precision end as wind_speed_kmh,
      case when kind='weather' then (payload->>'humidity_percent')::double precision end as humidity_percent
    from raw
  ), hs as materialized (
    select * from obs where kind='hotspot' and (p_district is null or district=p_district)
  ), pm as materialized (
    select * from obs where kind='pm25' and (measurement_kind in ('measured','model') or pid like 'CM-%')
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
          and c.status='received' and c.bbox='98.0086,17.2732,99.5730,20.1474' and c.retained_start<=d.lo and c.retained_end>=d.hi
          and c.checked_at>=least(d.hi,(u::date+1)::timestamp at time zone 'UTC')
          and (p_as_of is null or c.checked_at<=p_as_of))) as source_requests_complete
    from dates d
  ), per_day as (
    -- Every hotspot is already inside [p_start,p_end), so its Bangkok date is the coverage day it belongs to.
    select (observed_at at time zone 'Asia/Bangkok')::date as day,count(*) as n from hs group by 1
  ), daily as materialized (
    select c.day as date,c.partial_day,c.source_requests_complete,
      coalesce(p.n,0) as observed_count,
      case when coalesce(p.n,0)>0 or (c.source_requests_complete and not c.partial_day) then coalesce(p.n,0) else null end as count
    from coverage c left join per_day p on p.day=c.day
  ), districts as (
    select district as name,count(*) as count from hs group by 1
  ), hourly as (
    select extract(hour from observed_at at time zone 'Asia/Bangkok')::int as hour,count(*) as count from hs group by 1
  ), pm_days as (
    select (observed_at at time zone 'Asia/Bangkok')::date as date,
      case when measurement_kind='model' then 'model' else 'measured' end as measurement_kind,
      avg(pm25) as value,count(*) as samples,
      count(distinct pid) as stations from pm group by 1,2
  ), weather_days as (
    select (observed_at at time zone 'Asia/Bangkok')::date as date,
      case when measurement_kind='model' or source like 'Open-Meteo%' then 'model' else 'station' end as measurement_kind,
      max(temperature_c) as temp_max,min(temperature_c) as temp_min,
      max(wind_speed_kmh) as wind_max,avg(humidity_percent) as humidity,
      count(*) as samples,source from obs where kind='weather' group by 1,2,source
  ), source_rows as (
    select source,count(distinct observation_key) as count from public.cme_observations where kind='hotspot'
      and observed_at>=p_start and observed_at<p_end and (p_as_of is null or retrieved_at<=p_as_of)
      and (p_forest is null or p_forest=any(forest_ids))
      and (p_district is null or coalesce(nullif(payload->'spatial_assignment'->>'district',''),nullif(payload->>'district',''),'ไม่ระบุ')=p_district) group by source
  ), tambons as (
    select subdistrict as name,count(*) as count from hs group by 1
  ), forests as (
    select f as forest_id,count(*) as count from hs cross join lateral unnest(forest_ids) f group by 1
  ), hs_stats as (
    select count(*) as total,count(*) filter (where sa_status='matched') as spatial_matched,
      count(frp) as frp_known,max(frp) as frp_max,avg(frp) as frp_mean from hs
  )
  select jsonb_build_object('scope_bbox','98.0086,17.2732,99.5730,20.1474','start',p_start,'end',p_end,'as_of',p_as_of,
    'spatial_matched',(select spatial_matched from hs_stats),'total',(select total from hs_stats),'hotspots',coalesce((select jsonb_agg(to_jsonb(d) order by d.date) from daily d),'[]'),
    'districts',coalesce((select jsonb_agg(to_jsonb(d) order by d.count desc,d.name) from districts d),'[]'),
    'hour_histogram',(select jsonb_agg(coalesce(h.count,0) order by hours.hour) from generate_series(0,23) hours(hour) left join hourly h using(hour)),
    'satellites',(select coalesce(jsonb_agg(to_jsonb(s)), '[]') from (select coalesce(satellite,'ไม่ระบุ') name,count(*) count from hs group by 1) s),
    'confidence',(select jsonb_object_agg(native_level,n) from(select native_level,count(*) n from hs group by 1)c),
    'frp',jsonb_build_object('known',(select frp_known from hs_stats),
      'max',(select frp_max from hs_stats),'mean',(select frp_mean from hs_stats),
      'bins',(select jsonb_agg(n order by b) from(select bins.b,count(h.id) n from generate_series(0,6) bins(b)
        left join hs h on least(6,floor(h.frp/20)::int)=bins.b group by bins.b) z)),
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
revoke all on function public.cme_archive_analytics(timestamptz,timestamptz,timestamptz,text,text) from public,anon,authenticated;
grant execute on function public.cme_archive_analytics(timestamptz,timestamptz,timestamptz,text,text) to service_role;

commit;
