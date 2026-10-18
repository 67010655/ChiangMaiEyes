begin;
-- Exercise records are owned by a real signed-in account. Simulated actors
-- exist only inside this JSON and never enter memberships, incidents or mail.
create table public.cme_practice_runs (
  id uuid primary key, owner_id uuid not null references auth.users(id),
  version integer not null default 1 check(version>0), data jsonb not null,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check(jsonb_typeof(data)='object' and octet_length(data::text)<=200000)
);
create index cme_practice_owner on public.cme_practice_runs(owner_id,updated_at desc);
alter table public.cme_practice_runs enable row level security;
revoke all on public.cme_practice_runs from public,anon,authenticated;
grant select on public.cme_practice_runs to authenticated;
grant all on public.cme_practice_runs to service_role;
create policy cme_practice_owner_read on public.cme_practice_runs for select to authenticated using(owner_id=(select auth.uid()));

create function public.cme_practice_read(p_id uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
  if not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) then
    raise exception 'ยืนยันอีเมลก่อนใช้พื้นที่ซ้อม' using errcode='42501'; end if;
  if p_id is null then
    select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from
      (select id,version,data->>'title' as title,data->>'scenario' as scenario,created_at,updated_at from public.cme_practice_runs where owner_id=auth.uid() order by updated_at desc limit 100) x;
  else
    select to_jsonb(r)-'owner_id' into result from public.cme_practice_runs r where id=p_id and owner_id=auth.uid();
    if result is null then raise exception 'ไม่พบรอบซ้อมของบัญชีนี้' using errcode='P0002'; end if;
  end if;
  return result;
end $$;
create function public.cme_practice_save(p_id uuid,p_version integer,p_data jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare r public.cme_practice_runs%rowtype;
begin
  if not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) then
    raise exception 'ยืนยันอีเมลก่อนใช้พื้นที่ซ้อม' using errcode='42501'; end if;
  if p_data->>'mode' is distinct from 'practice' or jsonb_typeof(p_data) is distinct from 'object' or octet_length(p_data::text)>200000 then
    raise exception 'ข้อมูลรอบซ้อมไม่ถูกต้อง' using errcode='22023'; end if;
  perform pg_advisory_xact_lock(hashtext(auth.uid()::text));
  select * into r from public.cme_practice_runs where id=p_id for update;
  if found then
    if r.owner_id<>auth.uid() then raise exception 'ไม่มีสิทธิ์ในรอบซ้อมนี้' using errcode='42501'; end if;
    if r.data=p_data then return to_jsonb(r)-'owner_id'; end if;
    if r.version is distinct from p_version then raise exception 'รอบซ้อมมีการอัปเดตแล้ว โหลดล่าสุดก่อนส่งอีกครั้ง' using errcode='40001'; end if;
    update public.cme_practice_runs set data=p_data,version=version+1,updated_at=now() where id=p_id returning * into r;
  else
    if p_version<>0 then raise exception 'ไม่พบรอบซ้อมนี้' using errcode='P0002'; end if;
    if (select count(*) from public.cme_practice_runs where owner_id=auth.uid())>=100 then raise exception 'เก็บรอบซ้อมครบ 100 รอบแล้ว' using errcode='22023'; end if;
    insert into public.cme_practice_runs(id,owner_id,data) values(p_id,auth.uid(),p_data) returning * into r;
  end if;
  return to_jsonb(r)-'owner_id';
end $$;
revoke all on function public.cme_practice_read(uuid),public.cme_practice_save(uuid,integer,jsonb) from public,anon,authenticated;
grant execute on function public.cme_practice_read(uuid),public.cme_practice_save(uuid,integer,jsonb) to authenticated;

create table public.cme_field_checks (
  id uuid primary key, incident_id uuid not null references public.cme_incidents(id),
  recorded_by uuid not null references auth.users(id), data jsonb not null,
  corrects_id uuid references public.cme_field_checks(id), created_at timestamptz not null default now(),
  check(jsonb_typeof(data)='object' and octet_length(data::text)<=16000)
);
create index cme_field_checks_incident on public.cme_field_checks(incident_id,created_at);
alter table public.cme_field_checks enable row level security;
revoke all on public.cme_field_checks from public,anon,authenticated;
grant select on public.cme_field_checks to authenticated;
grant all on public.cme_field_checks to service_role;
create policy cme_field_checks_read on public.cme_field_checks for select to authenticated using(public.cme_can_read_incident(incident_id));
create function public.cme_field_check(p_incident uuid,p_id uuid default null,p_data jsonb default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare r public.cme_field_checks%rowtype; result jsonb; t timestamptz; k text;
begin
  if not public.cme_can_read_incident(p_incident) or not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) then
    raise exception 'ไม่มีสิทธิ์ดูผลตรวจเหตุนี้' using errcode='42501'; end if;
  if p_data is null then
    select coalesce(jsonb_agg(to_jsonb(x) order by x.created_at,x.id),'[]') into result from public.cme_field_checks x where incident_id=p_incident;
    return result;
  end if;
  perform 1 from public.cme_incidents where id=p_incident for update;
  if not public.cme_can_note(p_incident) then raise exception 'รับร่วมประสานก่อนบันทึกผลตรวจ' using errcode='42501'; end if;
  select * into r from public.cme_field_checks where id=p_id;
  if found then
    if r.incident_id<>p_incident or r.recorded_by<>auth.uid() or r.data<>p_data then raise exception 'รหัสการส่งนี้ถูกใช้แล้ว' using errcode='23505'; end if;
    return to_jsonb(r);
  end if;
  if p_data->>'outcome' is null or p_data->>'outcome' not in ('fire_found','no_fire_found','unverified') or
    p_data->>'method' is null or p_data->>'method' not in ('on_site','phone','photo','unavailable') or
    p_data->>'satellite_match' is null or p_data->>'satellite_match' not in ('matched','not_found','not_checked') or
    length(coalesce(p_data->>'note',''))<5 or length(p_data->>'note')>2000 or octet_length(p_data::text)>16000 or
    coalesce(p_data->>'checked_at','')!~'(Z|[+-][0-9]{2}:[0-9]{2})$' then
    raise exception 'ระบุผล วิธีตรวจ เวลาเขตไทย และหลักฐานให้ครบ' using errcode='22023'; end if;
  t:=(p_data->>'checked_at')::timestamptz;
  if t>now()+interval '5 minutes' then raise exception 'เวลาตรวจอยู่ในอนาคต' using errcode='22023'; end if;
  if p_data->>'method'='unavailable' and p_data->>'outcome'<>'unverified' then raise exception 'ยังไม่มีวิธีตรวจต้องเลือกยังตรวจไม่ได้' using errcode='22023'; end if;
  if jsonb_typeof(p_data)<>'object' or exists(select 1 from jsonb_object_keys(p_data) x where x not in
    ('corrects_id','checked_at','outcome','method','note','latitude','longitude','position_accuracy_m','satellite_match','satellite_source','satellite_detected_at','web_received_at','email_delivered_at','message_seen_at')) then
    raise exception 'รูปแบบผลตรวจไม่ถูกต้อง' using errcode='22023'; end if;
  if (nullif(p_data->>'latitude','') is null)<>(nullif(p_data->>'longitude','') is null) or
    (p_data->>'latitude')::double precision not between -90 and 90 or (p_data->>'longitude')::double precision not between -180 and 180 or
    (p_data->>'position_accuracy_m')::double precision not between 0 and 100000 or length(coalesce(p_data->>'satellite_source',''))>300 then
    raise exception 'พิกัดและความคลาดเคลื่อนตำแหน่งไม่ถูกต้อง' using errcode='22023'; end if;
  foreach k in array array['satellite_detected_at','web_received_at','email_delivered_at','message_seen_at'] loop
    if p_data->>k is not null and (p_data->>k!~'(Z|[+-][0-9]{2}:[0-9]{2})$' or (p_data->>k)::timestamptz>now()+interval '5 minutes') then
      raise exception 'เวลาต้องระบุเขตเวลาและไม่อยู่ในอนาคต' using errcode='22023'; end if;
  end loop;
  if p_data->>'satellite_match'='matched' and (nullif(p_data->>'satellite_source','') is null or nullif(p_data->>'satellite_detected_at','') is null) then raise exception 'ระบุแหล่งและเวลาจุดดาวเทียมที่เทียบ' using errcode='22023'; end if;
  if p_data->>'satellite_match'<>'matched' and p_data->>'satellite_detected_at' is not null or
    (p_data->>'web_received_at')::timestamptz<(p_data->>'satellite_detected_at')::timestamptz or
    (p_data->>'message_seen_at')::timestamptz<(p_data->>'email_delivered_at')::timestamptz then raise exception 'ลำดับเวลาของหลักฐานไม่ถูกต้อง' using errcode='22023'; end if;
  if nullif(p_data->>'corrects_id','') is not null and not exists(select 1 from public.cme_field_checks where id=(p_data->>'corrects_id')::uuid and incident_id=p_incident) then raise exception 'แก้ไขได้เฉพาะผลตรวจในเหตุเดียวกัน' using errcode='22023'; end if;
  if (select count(*) from public.cme_field_checks where incident_id=p_incident)>=500 then raise exception 'เก็บผลตรวจครบ 500 รายการในเหตุนี้แล้ว' using errcode='22023'; end if;
  insert into public.cme_field_checks(id,incident_id,recorded_by,data,corrects_id) values(p_id,p_incident,auth.uid(),p_data,nullif(p_data->>'corrects_id','')::uuid) returning * into r;
  perform public.cme_event(p_incident,'field_check','เพิ่มผลตรวจภาคสนาม (ผลบันทึกของผู้ใช้)');
  return to_jsonb(r);
end $$;
revoke all on function public.cme_field_check(uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.cme_field_check(uuid,uuid,jsonb) to authenticated;
commit;
