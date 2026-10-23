-- Pins show the latest progress note the reporter's forest wrote, so other forests see "fire spreading"
-- or "mostly out" without opening the (private) incident. Only the newest note, cut to 300 characters,
-- with the author's name and time. Everything else about the pin list is unchanged, and the incident,
-- its events and photos stay private to the forest.
begin;

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
      public.cme_can_read_incident(i.id) as can_open,
      (select jsonb_build_object('text',left(e.note,300),'at',e.created_at,'by',e.actor_name)
         from public.cme_incident_events e where e.incident_id=i.id and e.kind='note' and btrim(e.note)<>''
         order by e.created_at desc,e.id desc limit 1) as latest_note
    from public.cme_incidents i join public.cme_forests f using(forest_id) join auth.users c on c.id=i.created_by
    where i.status in ('pending','confirmed','coordinating','controlled') and i.linked_incident_id is null
      and i.created_at>now()-interval '3 days'
    order by i.created_at desc limit 300
  ) x),'[]'::jsonb);
end $$;
revoke all on function public.cme_open_pins() from public,anon,authenticated;
grant execute on function public.cme_open_pins() to authenticated;

commit;
