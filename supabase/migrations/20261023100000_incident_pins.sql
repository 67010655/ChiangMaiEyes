-- Incident pins: an incident a community-forest rep reports shows on the map for every approved
-- rep and admin. It stays open until the reporter (or an admin) ends it, or for 3 days at most.
-- Additive on purpose: nothing here replaces cme_action or widens cme_can_read_incident, so the
-- per-forest isolation of incidents, events, photos and field checks is unchanged. Other forests
-- see only the fixed fields returned by cme_open_pins().
begin;

alter table public.cme_incidents
  add column if not exists contact_phone text check (contact_phone is null or contact_phone ~ '^[0-9+()\- ]{6,20}$'),
  add column if not exists nearby jsonb;

create or replace function public.cme_is_any_member() returns boolean language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.cme_memberships where user_id=(select auth.uid()) and status='approved');
$$;
revoke all on function public.cme_is_any_member() from public,anon,authenticated;
grant execute on function public.cme_is_any_member() to authenticated;

-- Open pins for the map. Only an admin or a rep with at least one approved forest may call it.
create or replace function public.cme_open_pins() returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare u uuid:=auth.uid();
begin
  if u is null or not exists(select 1 from auth.users where id=u and email_confirmed_at is not null) then
    raise exception 'ต้องเข้าสู่ระบบด้วยอีเมลที่ยืนยันแล้ว' using errcode='42501'; end if;
  if not (public.cme_is_admin() or public.cme_is_any_member()) then
    raise exception 'สำหรับตัวแทนป่าที่ได้รับอนุมัติแล้ว' using errcode='42501'; end if;
  return coalesce((select jsonb_agg(to_jsonb(x) order by x.created_at desc) from (
    select i.id,i.forest_id,f.name as forest_name,f.amphoe,i.observation,i.latitude,i.longitude,i.observed_at,i.created_at,
      i.created_at+interval '3 days' as expires_at,i.description,i.contact_phone,i.status,i.nearby,
      coalesce(nullif(c.raw_user_meta_data->>'full_name',''),'ตัวแทนชุมชน') as reporter_name,
      (i.created_by=u) as mine,
      (i.created_by=u or public.cme_is_admin()) as can_close,
      public.cme_can_read_incident(i.id) as can_open
    from public.cme_incidents i join public.cme_forests f using(forest_id) join auth.users c on c.id=i.created_by
    where i.status in ('pending','confirmed','coordinating','controlled') and i.linked_incident_id is null
      and i.created_at>now()-interval '3 days'
    order by i.created_at desc limit 300
  ) x),'[]'::jsonb);
end $$;
revoke all on function public.cme_open_pins() from public,anon,authenticated;
grant execute on function public.cme_open_pins() to authenticated;

-- Only the reporter or an admin ends a pin. "closed" = the work is done, "cancelled" = it was not a fire.
create or replace function public.cme_close_incident(p_id uuid,p_outcome text,p_note text default '')
returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid:=auth.uid(); r public.cme_incidents%rowtype; n text:=trim(coalesce(p_note,'')); prev text;
begin
  if u is null or not exists(select 1 from auth.users where id=u and email_confirmed_at is not null) then
    raise exception 'ต้องเข้าสู่ระบบด้วยอีเมลที่ยืนยันแล้ว' using errcode='42501'; end if;
  if p_outcome not in ('closed','cancelled') then raise exception 'ผลลัพธ์ไม่ถูกต้อง' using errcode='22023'; end if;
  if length(n)>2000 then raise exception 'ข้อความยาวเกินกำหนด' using errcode='22023'; end if;
  select * into r from public.cme_incidents where id=p_id for update;
  if not found then raise exception 'ไม่พบเหตุ' using errcode='P0002'; end if;
  if not (r.created_by=u or public.cme_is_admin()) then
    raise exception 'เฉพาะคนที่แจ้งเหตุหรือผู้ดูแลระบบจึงปิดเหตุนี้ได้' using errcode='42501'; end if;
  if r.status in ('closed','cancelled') then raise exception 'เหตุนี้ปิดไปแล้ว' using errcode='22023'; end if;
  prev:=r.status;
  update public.cme_incidents set status=p_outcome,published=false,version=version+1,updated_at=now() where id=p_id returning * into r;
  perform public.cme_event(p_id,'status',coalesce(nullif(n,''),case when p_outcome='closed' then 'จบงาน' else 'ไม่ใช่ไฟ' end),prev,p_outcome);
  return to_jsonb(r);
end $$;
revoke all on function public.cme_close_incident(uuid,text,text) from public,anon,authenticated;
grant execute on function public.cme_close_incident(uuid,text,text) to authenticated;

-- Optional phone number for other reps to call; only the reporter sets or clears it.
create or replace function public.cme_set_incident_contact(p_id uuid,p_phone text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid:=auth.uid(); v text:=nullif(trim(coalesce(p_phone,'')),'');
begin
  if u is null or not exists(select 1 from auth.users where id=u and email_confirmed_at is not null) then
    raise exception 'ต้องเข้าสู่ระบบด้วยอีเมลที่ยืนยันแล้ว' using errcode='42501'; end if;
  if v is not null and v !~ '^[0-9+()\- ]{6,20}$' then raise exception 'เบอร์โทรไม่ถูกต้อง' using errcode='22023'; end if;
  update public.cme_incidents set contact_phone=v,updated_at=now() where id=p_id and created_by=u and status in ('pending','confirmed','coordinating','controlled');
  if not found then raise exception 'ตั้งเบอร์ได้เฉพาะเหตุที่คุณแจ้งและยังเปิดอยู่' using errcode='42501'; end if;
  return jsonb_build_object('ok',true);
end $$;
revoke all on function public.cme_set_incident_contact(uuid,text) from public,anon,authenticated;
grant execute on function public.cme_set_incident_contact(uuid,text) to authenticated;

-- Three days without an ending closes the pin. Backend worker only (service role).
-- cme_event needs auth.uid(), which a worker does not have, so the history row is written directly.
create or replace function public.cme_expire_incidents() returns jsonb
language plpgsql security definer set search_path='' as $$
declare r public.cme_incidents%rowtype; ids jsonb:='[]'::jsonb;
begin
  for r in select * from public.cme_incidents
    where status in ('pending','confirmed','coordinating','controlled') and created_at<=now()-interval '3 days' for update skip locked
  loop
    update public.cme_incidents set status='closed',published=false,version=version+1,updated_at=now() where id=r.id;
    insert into public.cme_incident_events(incident_id,actor_id,actor_name,kind,note,status_from,status_to)
    values(r.id,r.created_by,'ระบบอัตโนมัติ','expired','ครบ 3 วันโดยไม่มีการกดจบงาน ระบบปิดหมุดให้อัตโนมัติ',r.status,'closed');
    ids:=ids||jsonb_build_array(jsonb_build_object('id',r.id,'forest_id',r.forest_id,'created_by',r.created_by));
  end loop;
  return ids;
end $$;
revoke all on function public.cme_expire_incidents() from public,anon,authenticated;
grant execute on function public.cme_expire_incidents() to service_role;

-- At most 3 new pins per person per 24 hours (every pin alerts nearby forests by LINE).
create or replace function public.cme_limit_incident_rate() returns trigger
language plpgsql set search_path='' as $$
begin
  if (select count(*) from public.cme_incidents where created_by=new.created_by and created_at>now()-interval '24 hours')>=3 then
    raise exception 'แจ้งเหตุได้ไม่เกิน 3 ครั้งใน 24 ชั่วโมง ถ้าเห็นไฟเพิ่ม โทร 1362 หรือบอกผู้ดูแลระบบ' using errcode='22023';
  end if;
  return new;
end $$;
revoke all on function public.cme_limit_incident_rate() from public,anon,authenticated;
drop trigger if exists cme_incident_rate on public.cme_incidents;
create trigger cme_incident_rate before insert on public.cme_incidents for each row execute function public.cme_limit_incident_rate();

commit;
