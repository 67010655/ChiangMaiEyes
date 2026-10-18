begin;
alter table public.cme_incidents add column if not exists linked_incident_id uuid references public.cme_incidents(id);
create table if not exists public.cme_incident_photos(
  id uuid primary key, incident_id uuid not null references public.cme_incidents(id),
  uploaded_by uuid not null references auth.users(id), object_path text not null unique,
  created_at timestamptz not null default now()
);
create index if not exists cme_photos_incident on public.cme_incident_photos(incident_id,created_at);
alter table public.cme_incident_photos enable row level security;
revoke all on public.cme_incident_photos from public,anon,authenticated;
grant select on public.cme_incident_photos to authenticated;
grant all on public.cme_incident_photos to service_role;
create policy cme_photos_read on public.cme_incident_photos for select to authenticated using(public.cme_can_read_incident(incident_id));

create or replace function public.cme_can_note(p_id uuid) returns boolean
language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.cme_incidents i where i.id=p_id and (
    public.cme_is_admin() or public.cme_is_member(i.forest_id) or exists(
      select 1 from public.cme_incident_partners p where p.incident_id=i.id and p.status='accepted' and public.cme_is_member(p.forest_id))));
$$;
revoke all on function public.cme_can_note(uuid) from public,anon,authenticated;

create or replace function public.cme_add_photo(p_incident uuid,p_photo uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare r public.cme_incident_photos%rowtype; path text:=p_incident::text||'/'||p_photo::text||'.jpg';
begin
  perform 1 from public.cme_incidents where id=p_incident for update;
  if not public.cme_can_note(p_incident) or not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) then
    raise exception 'ไม่มีสิทธิ์เพิ่มรูปของเหตุนี้' using errcode='42501'; end if;
  if (select count(*) from public.cme_incident_photos where incident_id=p_incident)>=10 then
    raise exception 'เหตุนี้แนบรูปครบ 10 รูปแล้ว' using errcode='22023'; end if;
  if not exists(select 1 from storage.objects where bucket_id='cme-incident-evidence' and name=path) then
    raise exception 'ยังไม่ได้อัปโหลดรูป' using errcode='22023'; end if;
  insert into public.cme_incident_photos(id,incident_id,uploaded_by,object_path) values(p_photo,p_incident,auth.uid(),path) returning * into r;
  perform public.cme_event(p_incident,'photo','เพิ่มภาพประกอบเหตุ');
  update public.cme_incidents set version=version+1,updated_at=now() where id=p_incident;
  return to_jsonb(r);
end $$;
revoke all on function public.cme_add_photo(uuid,uuid) from public,anon,authenticated;
grant execute on function public.cme_add_photo(uuid,uuid) to authenticated;

create or replace function public.cme_claim_one_email(p_id uuid) returns setof public.cme_email_outbox
language sql security definer set search_path='' as $$
  update public.cme_email_outbox set status='processing',attempts=attempts+1,last_attempt_at=now(),lease_until=now()+interval '2 minutes'
  where id in (select id from public.cme_email_outbox where id=p_id and available_at<=now() and attempts<5 and
    (status='pending' or (status='processing' and lease_until<now())) for update skip locked) returning *;
$$;
revoke all on function public.cme_claim_one_email(uuid) from public,anon,authenticated;
grant execute on function public.cme_claim_one_email(uuid) to service_role;
commit;
