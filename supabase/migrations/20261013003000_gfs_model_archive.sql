begin;
-- Public scientific model data only. No user, incident, photo or email data.
create table public.cme_gfs_frames (
  id text primary key check(id ~ '^[a-f0-9]{64}$'),
  run_at timestamptz not null, valid_at timestamptz not null,
  retrieved_at timestamptz not null,
  first_stored_at timestamptz not null default clock_timestamp(),
  forecast_hour integer not null check(forecast_hour between 0 and 72),
  bbox text not null, cell_count integer not null check(cell_count between 1 and 400),
  status text not null check(status in ('available','partial')),
  source_url text not null check(source_url like 'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?%'),
  payload jsonb not null, grib bytea not null,
  check(valid_at=run_at+forecast_hour*interval '1 hour'),
  check(run_at<=retrieved_at),
  check(octet_length(payload::text)<=256000),
  check(octet_length(grib) between 20 and 2000000),
  check(id=encode(sha256(grib),'hex'))
);
create index cme_gfs_stored_time on public.cme_gfs_frames(first_stored_at desc,id);
create index cme_gfs_run_time on public.cme_gfs_frames(run_at,valid_at);
alter table public.cme_gfs_frames enable row level security;
revoke all on public.cme_gfs_frames from public,anon,authenticated;
grant select,insert on public.cme_gfs_frames to service_role;

create function public.cme_gfs_ingest(p_frame jsonb,p_grib_base64 text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare raw bytea; saved timestamptz; n integer;
begin
  if jsonb_typeof(p_frame) is distinct from 'object' or
     jsonb_typeof(p_frame->'cells') is distinct from 'array' or
     jsonb_typeof(p_frame->'field_metadata') is distinct from 'array' or
     jsonb_array_length(p_frame->'field_metadata')<>4 or
     p_frame->>'measurement_kind' is distinct from 'model' or
     p_frame->>'publisher' is distinct from 'NOAA NCEP' or
     p_frame->>'product' is distinct from 'GFS 0.25° PBL' or
     p_grib_base64 is null or octet_length(p_grib_base64)>2700000 or
     (p_frame->>'retrieved_at')::timestamptz>now()+interval '5 minutes' then
    raise exception 'invalid GFS model frame' using errcode='22023';
  end if;
  raw:=decode(p_grib_base64,'base64');
  if substring(raw from 1 for 4)<>decode('47524942','hex') or
     substring(raw from octet_length(raw)-3 for 4)<>decode('37373737','hex') then
    raise exception 'invalid GRIB evidence' using errcode='22023';
  end if;
  insert into public.cme_gfs_frames(id,run_at,valid_at,retrieved_at,forecast_hour,bbox,cell_count,status,source_url,payload,grib)
  values(p_frame->>'sha256',(p_frame->>'run_at')::timestamptz,(p_frame->>'valid_at')::timestamptz,
    (p_frame->>'retrieved_at')::timestamptz,(p_frame->>'forecast_hour')::integer,p_frame->>'bbox',
    jsonb_array_length(p_frame->'cells'),p_frame->>'status',p_frame->>'source_url',p_frame,raw)
  on conflict(id) do nothing;
  get diagnostics n=row_count;
  select first_stored_at into saved from public.cme_gfs_frames where id=p_frame->>'sha256';
  return jsonb_build_object('id',p_frame->>'sha256','inserted',n,'first_stored_at',saved);
end $$;

create function public.cme_gfs_read(p_start timestamptz,p_as_of timestamptz,p_offset integer default 0,p_limit integer default 20) returns jsonb
language plpgsql stable security definer set search_path='' as $$
begin
  if p_start is null or p_as_of is null or p_as_of<=p_start or p_as_of-p_start>interval '367 days' or
     p_as_of>now()+interval '5 minutes' or p_offset is null or p_offset<0 or p_offset>1000000 or
     p_limit is null or p_limit<1 or p_limit>100 then
    raise exception 'invalid GFS archive window' using errcode='22023';
  end if;
  return jsonb_build_object('total',(select count(*) from public.cme_gfs_frames where first_stored_at>=p_start and first_stored_at<=p_as_of),
    'first_stored_at',(select min(first_stored_at) from public.cme_gfs_frames where first_stored_at<=p_as_of),
    'frames',coalesce((select jsonb_agg(to_jsonb(q)) from(
      select id,run_at,valid_at,retrieved_at,first_stored_at,forecast_hour,bbox,cell_count,status,source_url,
        payload->'reference_cell' as reference_cell
      from public.cme_gfs_frames where first_stored_at>=p_start and first_stored_at<=p_as_of
      order by first_stored_at desc,id offset p_offset limit p_limit
    ) q),'[]'));
end $$;

create function public.cme_gfs_frame(p_id text,p_as_of timestamptz) returns jsonb
language plpgsql stable security definer set search_path='' as $$
begin
  if p_id is null or p_id !~ '^[a-f0-9]{64}$' or p_as_of is null or p_as_of>now()+interval '5 minutes' then
    raise exception 'invalid GFS evidence cutoff' using errcode='22023';
  end if;
  return (select jsonb_build_object('id',id,'first_stored_at',first_stored_at,'frame',payload)
    from public.cme_gfs_frames where id=p_id and first_stored_at<=p_as_of);
end $$;

revoke all on function public.cme_gfs_ingest(jsonb,text),public.cme_gfs_read(timestamptz,timestamptz,integer,integer),public.cme_gfs_frame(text,timestamptz) from public,anon,authenticated;
grant execute on function public.cme_gfs_ingest(jsonb,text),public.cme_gfs_read(timestamptz,timestamptz,integer,integer),public.cme_gfs_frame(text,timestamptz) to service_role;
notify pgrst,'reload schema';
commit;
