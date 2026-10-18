-- Additive community workflow. Legacy rows remain intact.
-- Apply after the data/policy backup; seed cme_forests from the 677 RECOFTC records.
begin;

create table if not exists public.cme_forests (
  forest_id text primary key, name text not null, amphoe text not null,
  source text not null default 'RECOFTC boundary dataset'
);
create table if not exists public.cme_admins (
  user_id uuid primary key references auth.users(id), created_at timestamptz not null default now()
);
create table if not exists public.cme_memberships (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id),
  forest_id text not null references public.cme_forests(forest_id),
  status text not null default 'pending' check (status in ('pending','approved','rejected','revoked')),
  request_note text not null default '' check (length(request_note)<=1000),
  review_note text not null default '' check (length(review_note)<=1000),
  reviewed_by uuid references auth.users(id), reviewed_at timestamptz,
  created_at timestamptz not null default now(), unique(user_id,forest_id)
);
create index if not exists cme_memberships_forest_status on public.cme_memberships(forest_id,status,user_id);
create table if not exists public.cme_incidents (
  id uuid primary key, forest_id text not null references public.cme_forests(forest_id),
  created_by uuid not null references auth.users(id), coordinator_id uuid references auth.users(id),
  observation text not null check(observation in ('smoke','fire')),
  latitude double precision not null check(latitude between -90 and 90),
  longitude double precision not null check(longitude between -180 and 180),
  observed_at timestamptz not null, description text not null default '' check(length(description)<=2000),
  status text not null default 'pending' check(status in ('pending','confirmed','coordinating','controlled','closed','cancelled')),
  published boolean not null default false, version integer not null default 1,
  request_hash text not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists cme_incidents_forest_updated on public.cme_incidents(forest_id,updated_at desc);
create index if not exists cme_incidents_creator_created on public.cme_incidents(created_by,created_at desc);
create table if not exists public.cme_incident_partners (
  incident_id uuid not null references public.cme_incidents(id), forest_id text not null references public.cme_forests(forest_id),
  status text not null default 'invited' check(status in ('invited','accepted','declined')),
  invited_by uuid not null references auth.users(id), responded_by uuid references auth.users(id),
  created_at timestamptz not null default now(), responded_at timestamptz, primary key(incident_id,forest_id)
);
create index if not exists cme_partners_forest on public.cme_incident_partners(forest_id,incident_id);
create table if not exists public.cme_incident_events (
  id uuid primary key default gen_random_uuid(), incident_id uuid not null references public.cme_incidents(id),
  actor_id uuid not null references auth.users(id), actor_name text not null,
  kind text not null, note text not null default '' check(length(note)<=2000),
  status_from text, status_to text, created_at timestamptz not null default now()
);
create index if not exists cme_events_incident_time on public.cme_incident_events(incident_id,created_at,id);
create table if not exists public.cme_notification_preferences (
  user_id uuid primary key references auth.users(id), events_enabled boolean not null default false,
  daily_enabled boolean not null default false, quiet_enabled boolean not null default false,
  quiet_start integer not null default 21 check(quiet_start between 0 and 23),
  quiet_end integer not null default 7 check(quiet_end between 0 and 23),
  updated_at timestamptz not null default now()
);
create table if not exists public.cme_email_outbox (
  id uuid primary key default gen_random_uuid(), dedup_key text not null unique,
  user_id uuid not null references auth.users(id), forest_id text references public.cme_forests(forest_id),
  category text not null check(category in ('incident','hotspot','daily','test')),
  recipient text not null, subject text not null, body_html text not null,
  status text not null default 'pending' check(status in ('pending','processing','sent','failed','suppressed')),
  attempts integer not null default 0, available_at timestamptz not null default now(),
  lease_until timestamptz, first_attempt_at timestamptz, last_attempt_at timestamptz, provider_id text unique, delivery_status text,
  last_error text, created_at timestamptz not null default now(), sent_at timestamptz
);
create index if not exists cme_outbox_available on public.cme_email_outbox(available_at,created_at) where status in ('pending','processing');
create table if not exists public.cme_webhook_receipts (
  id text primary key, created_at timestamptz not null default now()
);
create table if not exists public.cme_job_runs (
  job_key text primary key, started_at timestamptz not null default now(), completed_at timestamptz
);

alter table public.cme_forests enable row level security;
alter table public.cme_admins enable row level security;
alter table public.cme_memberships enable row level security;
alter table public.cme_incidents enable row level security;
alter table public.cme_incident_partners enable row level security;
alter table public.cme_incident_events enable row level security;
alter table public.cme_notification_preferences enable row level security;
alter table public.cme_email_outbox enable row level security;
alter table public.cme_webhook_receipts enable row level security;
alter table public.cme_job_runs enable row level security;

-- No client can insert a privileged role, review flag, event, or outbox row.
do $$ declare t text; begin
  foreach t in array array['cme_forests','cme_admins','cme_memberships','cme_incidents','cme_incident_partners','cme_incident_events','cme_notification_preferences','cme_email_outbox','cme_webhook_receipts','cme_job_runs'] loop
    execute format('revoke all on public.%I from public, anon, authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;

create or replace function public.cme_is_admin() returns boolean language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.cme_admins where user_id=(select auth.uid()));
$$;
create or replace function public.cme_is_member(p_forest text) returns boolean language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.cme_memberships where user_id=(select auth.uid()) and forest_id=p_forest and status='approved');
$$;
create or replace function public.cme_can_read_incident(p_id uuid) returns boolean language sql stable security definer set search_path='' as $$
  select public.cme_is_admin() or exists(select 1 from public.cme_incidents i where i.id=p_id and
    (public.cme_is_member(i.forest_id) or exists(select 1 from public.cme_incident_partners p where p.incident_id=i.id and p.status in ('invited','accepted') and public.cme_is_member(p.forest_id))));
$$;
create or replace function public.cme_manages_incident(p_id uuid) returns boolean language sql stable security definer set search_path='' as $$
  select public.cme_is_admin() or exists(select 1 from public.cme_incidents i where i.id=p_id and
    (public.cme_is_member(i.forest_id) or (i.coordinator_id=(select auth.uid()) and public.cme_can_read_incident(i.id))));
$$;
revoke all on function public.cme_is_admin(),public.cme_is_member(text),public.cme_can_read_incident(uuid),public.cme_manages_incident(uuid) from public,anon,authenticated;
grant execute on function public.cme_is_admin(),public.cme_is_member(text),public.cme_can_read_incident(uuid),public.cme_manages_incident(uuid) to authenticated;
grant select on public.cme_forests to anon,authenticated;
grant select on public.cme_memberships,public.cme_incidents,public.cme_incident_partners,public.cme_incident_events,public.cme_notification_preferences to authenticated;
create policy cme_forests_read on public.cme_forests for select to anon,authenticated using(true);
create policy cme_memberships_read on public.cme_memberships for select to authenticated using(user_id=(select auth.uid()) or public.cme_is_admin());
create policy cme_incidents_read on public.cme_incidents for select to authenticated using(public.cme_can_read_incident(id));
create policy cme_partners_read on public.cme_incident_partners for select to authenticated using(public.cme_can_read_incident(incident_id));
create policy cme_events_read on public.cme_incident_events for select to authenticated using(public.cme_can_read_incident(incident_id));
create policy cme_preferences_read on public.cme_notification_preferences for select to authenticated using(user_id=(select auth.uid()));

create or replace function public.cme_event(p_id uuid,p_kind text,p_note text default '',p_from text default null,p_to text default null)
returns void language plpgsql security definer set search_path='' as $$
begin
  insert into public.cme_incident_events(incident_id,actor_id,actor_name,kind,note,status_from,status_to)
  select p_id,auth.uid(),coalesce(nullif(raw_user_meta_data->>'full_name',''),'ตัวแทนชุมชน'),p_kind,coalesce(p_note,''),p_from,p_to from auth.users where id=auth.uid();
end $$;
revoke all on function public.cme_event(uuid,text,text,text,text) from public,anon,authenticated;

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

create or replace function public.cme_public_incidents() returns jsonb language sql stable security definer set search_path='' as $$
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') from (
    select i.id,i.forest_id,f.name as forest_name,f.amphoe,i.status,i.observed_at,i.updated_at
    from public.cme_incidents i join public.cme_forests f using(forest_id) where published and status<>'pending' order by updated_at desc limit 100
  ) x;
$$;
revoke all on function public.cme_public_incidents() from public,anon,authenticated;
grant execute on function public.cme_public_incidents() to anon,authenticated;

-- A worker lease prevents concurrent consumers from taking the same outbox row.
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

-- Legacy reports are available privately through cme_action; nothing is deleted.
alter table public.manual_hotspot_reports add column if not exists cancelled_at timestamptz;
-- Legacy client grants are tightened in the cutover migration after the new UI/API deploy.

-- Harden older scaffold tables only if they exist in another environment.
do $$ begin
  if to_regclass('public.profiles') is not null then
    revoke insert,update on public.profiles from authenticated;
    grant update(display_name) on public.profiles to authenticated;
  end if;
  if to_regclass('public.field_reports') is not null then
    revoke insert,update on public.field_reports from authenticated;
    grant insert(user_id,forest_id,report_type,patrol_count,firebreak_km,fuel_management_rai,water_points_checked,committee_meeting,community_use_activity,no_burn_agreement,latitude,longitude,note,evidence_url) on public.field_reports to authenticated;
    grant update(note,evidence_url) on public.field_reports to authenticated;
  end if;
end $$;
notify pgrst,'reload schema';
commit;
