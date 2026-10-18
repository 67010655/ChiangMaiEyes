begin;
create or replace function public.cme_action(p_action text,p_payload jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare
  u uuid:=auth.uid(); a boolean; f text:=p_payload->>'forest_id';
  r public.cme_incidents%rowtype; i uuid; membership_row public.cme_memberships%rowtype;
  s text:=p_payload->>'status'; n text:=trim(coalesce(p_payload->>'note','')); v integer;
  partners jsonb; events jsonb; pref jsonb; result jsonb;
begin
  if u is null or not exists(select 1 from auth.users where id=u and email_confirmed_at is not null) then
    raise exception 'ต้องเข้าสู่ระบบด้วยอีเมลที่ยืนยันแล้ว' using errcode='42501';
  end if;
  a:=public.cme_is_admin();
  if length(n)>2000 then raise exception 'ข้อความยาวเกินกำหนด' using errcode='22023'; end if;

  if p_action='me' then
    select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
      select m.*,f.name,f.amphoe from public.cme_memberships m join public.cme_forests f using(forest_id) where m.user_id=u order by f.name
    ) x;
    select to_jsonb(p) into pref from public.cme_notification_preferences p where user_id=u;
    return jsonb_build_object('is_admin',a,'memberships',result,'preferences',coalesce(pref,'{"events_enabled":false,"daily_enabled":false,"quiet_enabled":false,"quiet_start":21,"quiet_end":7}'));
  elsif p_action='request_membership' then
    perform pg_advisory_xact_lock(hashtext(u::text));
    if length(n)>1000 then raise exception 'คำขอยาวเกินกำหนด' using errcode='22023'; end if;
    select * into membership_row from public.cme_memberships where user_id=u and forest_id=f for update;
    if found then return to_jsonb(membership_row); end if;
    if (select count(*) from public.cme_memberships where user_id=u and status='pending')>=5 then
      raise exception 'มีคำขอรอตรวจสอบครบ 5 พื้นที่แล้ว' using errcode='22023';
    end if;
    insert into public.cme_memberships(user_id,forest_id,request_note) values(u,f,n) returning * into membership_row;
    return to_jsonb(membership_row);
  elsif p_action='review_queue' then
    if not a then raise exception 'สำหรับผู้ดูแลระบบ' using errcode='42501'; end if;
    select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
      select m.*,f.name,f.amphoe,u.email,coalesce(u.raw_user_meta_data->>'full_name','') as display_name
      from public.cme_memberships m join public.cme_forests f using(forest_id) join auth.users u on u.id=m.user_id
      where m.status in ('pending','approved') order by m.created_at limit 200
    ) x; return result;
  elsif p_action='review_membership' then
    if not a then raise exception 'สำหรับผู้ดูแลระบบ' using errcode='42501'; end if;
    if s not in ('approved','rejected','revoked') or s is null or length(n)>1000 then raise exception 'สถานะไม่ถูกต้อง' using errcode='22023'; end if;
    update public.cme_memberships set status=s,review_note=n,reviewed_by=u,reviewed_at=now() where id=(p_payload->>'id')::uuid returning * into membership_row;
    if not found then raise exception 'ไม่พบคำขอ' using errcode='P0002'; end if;
    return to_jsonb(membership_row);
  elsif p_action='preferences' then
    insert into public.cme_notification_preferences(user_id,events_enabled,daily_enabled,quiet_enabled,quiet_start,quiet_end)
    values(u,coalesce((p_payload->>'events_enabled')::boolean,false),coalesce((p_payload->>'daily_enabled')::boolean,false),
      coalesce((p_payload->>'quiet_enabled')::boolean,false),coalesce((p_payload->>'quiet_start')::integer,21),coalesce((p_payload->>'quiet_end')::integer,7))
    on conflict(user_id) do update set events_enabled=excluded.events_enabled,daily_enabled=excluded.daily_enabled,
      quiet_enabled=excluded.quiet_enabled,quiet_start=excluded.quiet_start,quiet_end=excluded.quiet_end,updated_at=now()
    returning to_jsonb(cme_notification_preferences.*) into pref; return pref;
  elsif p_action='list_incidents' then
    select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
      select i.*,cf.name as forest_name,coalesce(c.raw_user_meta_data->>'full_name','ตัวแทนชุมชน') as coordinator_name,
        coalesce((select jsonb_agg(p.forest_id) from public.cme_incident_partners p where p.incident_id=i.id and p.status in ('invited','accepted')),'[]') as partner_forest_ids
      from public.cme_incidents i join public.cme_forests cf using(forest_id) left join auth.users c on c.id=i.coordinator_id
      where public.cme_can_read_incident(i.id) and (nullif(p_payload->>'forest_id','') is null or i.forest_id=f or
        exists(select 1 from public.cme_incident_partners p where p.incident_id=i.id and p.forest_id=f and p.status in ('invited','accepted')))
      order by i.updated_at desc,i.id desc limit 200 offset least(greatest(coalesce((p_payload->>'offset')::integer,0),0),100000)
    ) x; return result;
  elsif p_action='create_incident' then
    if not (a or public.cme_is_member(f)) then raise exception 'พื้นที่นี้ยังไม่ได้อนุมัติสิทธิ์ของคุณ' using errcode='42501'; end if;
    perform pg_advisory_xact_lock(hashtext(u::text));
    i:=(p_payload->>'id')::uuid;
    select * into r from public.cme_incidents where id=i;
    if found then
      if r.created_by<>u or r.request_hash<>md5(p_payload::text) then raise exception 'รหัสการส่งนี้ถูกใช้แล้ว' using errcode='23505'; end if;
      return to_jsonb(r);
    end if;
    if (p_payload->>'observed_at')::timestamptz>now()+interval '5 minutes' then raise exception 'เวลาที่พบเหตุอยู่ในอนาคต' using errcode='22023'; end if;
    if (select count(*) from public.cme_incidents where created_by=u and created_at>now()-interval '24 hours')>=30 then raise exception 'ส่งเหตุครบจำนวนต่อวันแล้ว' using errcode='22023'; end if;
    insert into public.cme_incidents(id,forest_id,created_by,observation,latitude,longitude,observed_at,description,request_hash)
    values(i,f,u,p_payload->>'observation',(p_payload->>'latitude')::double precision,(p_payload->>'longitude')::double precision,
      (p_payload->>'observed_at')::timestamptz,coalesce(p_payload->>'description',''),md5(p_payload::text)) returning * into r;
    perform public.cme_event(i,'created',r.description,null,'pending'); return to_jsonb(r);
  elsif p_action='my_reports' then
    select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
      select id,latitude,longitude,amphoe,tambon,description,reported_at,cancelled_at from public.manual_hotspot_reports where reporter_id=u order by reported_at desc limit 200
    ) x; return result;
  elsif p_action='cancel_legacy' then
    update public.manual_hotspot_reports set cancelled_at=now() where id=(p_payload->>'id')::uuid and reporter_id=u and cancelled_at is null;
    return jsonb_build_object('cancelled',found);
  end if;

  i:=(p_payload->>'id')::uuid;
  if p_action='merge_incident' then
    perform 1 from public.cme_incidents where id in (i,(p_payload->>'target_id')::uuid) order by id for update;
  end if;
  select * into r from public.cme_incidents where id=i for update;
  if not found then raise exception 'ไม่พบเหตุ' using errcode='P0002'; end if;
  if not public.cme_can_read_incident(i) then raise exception 'คุณไม่มีสิทธิ์ดูเหตุนี้' using errcode='42501'; end if;
  if p_action='incident_detail' then
    select coalesce(jsonb_agg(to_jsonb(x)),'[]') into partners from (select p.*,f.name from public.cme_incident_partners p join public.cme_forests f using(forest_id) where incident_id=i order by created_at) x;
    select coalesce(jsonb_agg(to_jsonb(x) order by x.created_at desc,x.id desc),'[]') into events from (select * from public.cme_incident_events where incident_id=i order by created_at desc,id desc limit 200) x;
    return jsonb_build_object('incident',to_jsonb(r),'partners',partners,'events',events,'can_manage',public.cme_manages_incident(i),
      'can_note',public.cme_can_note(i),'photos',coalesce((select jsonb_agg(jsonb_build_object('id',p.id,'created_at',p.created_at) order by p.created_at) from public.cme_incident_photos p where p.incident_id=i),'[]'));
  elsif p_action='incident_events' then
    select coalesce(jsonb_agg(to_jsonb(x) order by x.created_at desc,x.id desc),'[]') into events from (
      select * from public.cme_incident_events where incident_id=i order by created_at desc,id desc limit 200
      offset least(greatest(coalesce((p_payload->>'offset')::integer,0),0),100000)) x;
    return events;
  elsif p_action='add_note' then
    if n='' then raise exception 'กรอกบันทึกก่อนส่ง' using errcode='22023'; end if;
    if not public.cme_can_note(i) then raise exception 'ต้องรับร่วมประสานก่อนบันทึก' using errcode='42501'; end if;
    perform public.cme_event(i,'note',n);
  elsif p_action='respond_partner' then
    if not public.cme_is_member(f) and not a then raise exception 'คุณไม่มีสิทธิ์รับเรื่องแทนพื้นที่นี้' using errcode='42501'; end if;
    if s not in ('accepted','declined') or s is null then raise exception 'สถานะไม่ถูกต้อง' using errcode='22023'; end if;
    update public.cme_incident_partners set status=s,responded_by=u,responded_at=now() where incident_id=i and forest_id=f and status='invited';
    if not found then raise exception 'คำขอนี้ได้รับคำตอบแล้ว' using errcode='40001'; end if;
    perform public.cme_event(i,'partner_'||s,coalesce((select name from public.cme_forests where forest_id=f),'')||' '||n);
  else
    if not public.cme_manages_incident(i) then raise exception 'สำหรับตัวแทนพื้นที่หรือผู้รับประสาน' using errcode='42501'; end if;
    v:=(p_payload->>'version')::integer;
    if v is null or v<>r.version then raise exception 'ข้อมูลเปลี่ยนแล้ว กรุณาโหลดเหตุอีกครั้ง' using errcode='40001'; end if;
    if p_action='merge_incident' then
      if r.status<>'pending' or n='' or r.linked_incident_id is not null then raise exception 'เชื่อมได้เฉพาะรายงานที่รอตรวจสอบและต้องระบุเหตุผล' using errcode='22023'; end if;
      if not exists(select 1 from public.cme_incidents t where t.id=(p_payload->>'target_id')::uuid and t.id<>i and t.linked_incident_id is null and t.status not in ('closed','cancelled') and public.cme_manages_incident(t.id)) then
        raise exception 'เลือกเหตุที่ยังเปิดและคุณมีสิทธิ์จัดการ' using errcode='42501'; end if;
      update public.cme_incidents set status='cancelled',published=false,linked_incident_id=(p_payload->>'target_id')::uuid where id=i;
      perform public.cme_event(i,'merged',n||' · เหตุหลัก '||(p_payload->>'target_id'),r.status,'cancelled');
      perform public.cme_event((p_payload->>'target_id')::uuid,'linked_report',n||' · รายงานต้นทาง '||i::text);
      update public.cme_incidents set version=version+1,updated_at=now() where id=(p_payload->>'target_id')::uuid;
    elsif p_action='change_status' then
      if r.linked_incident_id is not null then raise exception 'รายงานนี้เชื่อมกับเหตุหลักแล้ว ให้ติดตามเหตุหลัก' using errcode='22023'; end if;
      if n='' then raise exception 'ระบุเหตุผลหรือผลการตรวจสอบ' using errcode='22023'; end if;
      if not ((r.status='pending' and s in ('confirmed','cancelled')) or (r.status='confirmed' and s in ('coordinating','controlled','cancelled')) or
        (r.status='coordinating' and s in ('controlled','cancelled')) or (r.status='controlled' and s in ('coordinating','closed')) or
        (r.status in ('closed','cancelled') and s='pending')) then raise exception 'เปลี่ยนสถานะตามขั้นตอนที่กำหนด' using errcode='22023'; end if;
      update public.cme_incidents set status=s,published=case when s='pending' then false else published end where id=i;
      perform public.cme_event(i,'status',n,r.status,s);
    elsif p_action='claim_coordination' then
      if r.coordinator_id is not null and r.coordinator_id<>u then raise exception 'มีผู้รับประสานแล้ว' using errcode='40001'; end if;
      update public.cme_incidents set coordinator_id=u where id=i;
      perform public.cme_event(i,'coordination','รับเป็นผู้ประสานเหตุในระบบ');
    elsif p_action='invite_partner' then
      if f=r.forest_id then raise exception 'เลือกชุมชนอื่นเพื่อขอร่วมประสาน' using errcode='22023'; end if;
      insert into public.cme_incident_partners(incident_id,forest_id,invited_by) values(i,f,u) on conflict do nothing;
      if not found then return to_jsonb(r); end if;
      perform public.cme_event(i,'partner_invited',(select name from public.cme_forests where forest_id=f)||' '||n);
    elsif p_action='publish_summary' then
      if r.status='pending' then raise exception 'รอการยืนยันเหตุก่อนเผยแพร่' using errcode='22023'; end if;
      update public.cme_incidents set published=coalesce((p_payload->>'published')::boolean,false) where id=i;
      perform public.cme_event(i,'publication',case when (p_payload->>'published')::boolean then 'เผยแพร่สรุปชื่อป่า สถานะ และเวลา' else 'ยกเลิกการเผยแพร่สรุป' end);
    else raise exception 'คำสั่งไม่ถูกต้อง' using errcode='22023'; end if;
  end if;
  update public.cme_incidents set version=version+1,updated_at=now() where id=i returning * into r;
  return to_jsonb(r);
end $$;
revoke all on function public.cme_action(text,jsonb) from public,anon,authenticated;
grant execute on function public.cme_action(text,jsonb) to authenticated;

create or replace function public.cme_claim_emails(p_limit integer default 10) returns setof public.cme_email_outbox
language sql security definer set search_path='' as $$
  update public.cme_email_outbox set status='failed',last_error='Worker retry limit reached',lease_until=null where status='processing' and lease_until<now() and attempts>=5;
  update public.cme_email_outbox set status='processing',attempts=attempts+1,last_attempt_at=now(),lease_until=now()+interval '2 minutes'
  where id in (select id from public.cme_email_outbox where available_at<=now() and attempts<5 and
    (status='pending' or (status='processing' and lease_until<now())) order by created_at for update skip locked limit least(greatest(p_limit,1),20))
  returning *;
$$;
revoke all on function public.cme_claim_emails(integer) from public,anon,authenticated;
grant execute on function public.cme_claim_emails(integer) to service_role;

commit;
