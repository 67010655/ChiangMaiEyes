begin;
-- LINE Official Account alerts. A LINE userId is personal data: these tables
-- are service-role only and never exposed through PostgREST to clients.
create table if not exists public.cme_line_links (
  user_id uuid primary key references auth.users(id) on delete cascade,
  line_user_id text not null unique check(line_user_id ~ '^U[0-9a-f]{32}$'),
  linked_at timestamptz not null default now()
);
create table if not exists public.cme_line_link_codes (
  code_hash text primary key check(code_hash ~ '^[0-9a-f]{64}$'),
  user_id uuid not null references auth.users(id) on delete cascade,
  expires_at timestamptz not null, used_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists cme_line_codes_user on public.cme_line_link_codes(user_id);
create table if not exists public.cme_line_outbox (
  id uuid primary key default gen_random_uuid(), dedup_key text not null unique,
  user_id uuid not null references auth.users(id) on delete cascade, forest_id text references public.cme_forests(forest_id),
  category text not null check(category in ('incident','hotspot','test')),
  message text not null check(length(message) between 1 and 4000),
  status text not null default 'pending' check(status in ('pending','processing','sent','failed','suppressed')),
  attempts integer not null default 0, available_at timestamptz not null default now(),
  lease_until timestamptz, first_attempt_at timestamptz, last_attempt_at timestamptz,
  retry_key uuid not null default gen_random_uuid(), last_error text,
  created_at timestamptz not null default now(), sent_at timestamptz
);
create index if not exists cme_line_outbox_available on public.cme_line_outbox(available_at,created_at) where status in ('pending','processing');

alter table public.cme_line_links enable row level security;
alter table public.cme_line_link_codes enable row level security;
alter table public.cme_line_outbox enable row level security;
revoke all on public.cme_line_links,public.cme_line_link_codes,public.cme_line_outbox from public,anon,authenticated;
grant all on public.cme_line_links,public.cme_line_link_codes,public.cme_line_outbox to service_role;

-- One-time code redemption. Codes expire after ten minutes and are single use;
-- a LINE account can belong to one web account at a time.
create or replace function public.cme_line_redeem(p_code_hash text,p_line_user_id text)
returns text language plpgsql security definer set search_path='' as $$
declare u uuid;
begin
  if p_line_user_id !~ '^U[0-9a-f]{32}$' then return 'invalid'; end if;
  update public.cme_line_link_codes set used_at=now()
    where code_hash=p_code_hash and used_at is null and expires_at>now()
    returning user_id into u;
  if u is null then return 'invalid'; end if;
  delete from public.cme_line_links where line_user_id=p_line_user_id and user_id<>u;
  insert into public.cme_line_links(user_id,line_user_id) values(u,p_line_user_id)
    on conflict(user_id) do update set line_user_id=excluded.line_user_id,linked_at=now();
  delete from public.cme_line_link_codes where user_id=u and code_hash<>p_code_hash;
  return 'linked';
end $$;
revoke all on function public.cme_line_redeem(text,text) from public,anon,authenticated;
grant execute on function public.cme_line_redeem(text,text) to service_role;

create or replace function public.cme_claim_line(p_limit integer default 5) returns setof public.cme_line_outbox
language sql security definer set search_path='' as $$
  update public.cme_line_outbox set status='failed',last_error='Worker retry limit reached',lease_until=null where status='processing' and lease_until<now() and attempts>=5;
  update public.cme_line_outbox set status='processing',attempts=attempts+1,last_attempt_at=now(),lease_until=now()+interval '2 minutes'
  where id in (select id from public.cme_line_outbox where available_at<=now() and attempts<5 and
    (status='pending' or (status='processing' and lease_until<now())) order by created_at for update skip locked limit least(greatest(p_limit,1),20))
  returning *;
$$;
revoke all on function public.cme_claim_line(integer) from public,anon,authenticated;
grant execute on function public.cme_claim_line(integer) to service_role;

-- Hotspot alerts: the observation is marked seen and every channel's message
-- is queued in one transaction, so a seen observation never loses its LINE
-- alert. Linking LINE is itself the opt-in for urgent LINE alerts.
drop function if exists public.cme_enqueue_hotspots(text,jsonb,text,text);
create or replace function public.cme_enqueue_hotspots(p_forest text,p_observations jsonb,p_subject text,p_html text,p_line_text text default null)
returns integer language plpgsql security definer set search_path='' as $$
declare o jsonb; keys text[]:=array[]::text[]; queued integer:=0; extra integer; signature text;
begin
  if not exists(select 1 from public.cme_memberships m left join public.cme_notification_preferences p using(user_id)
    left join public.cme_line_links l using(user_id)
    where m.forest_id=p_forest and m.status='approved' and (coalesce(p.events_enabled,false) or (p_line_text is not null and l.user_id is not null))) then return 0; end if;
  for o in select value from jsonb_array_elements(p_observations) loop
    if (o->>'observed_at')::timestamptz between now()-interval '24 hours' and now() then
      insert into public.cme_hotspot_seen(forest_id,event_key,observed_at) values(p_forest,o->>'event_key',(o->>'observed_at')::timestamptz) on conflict do nothing;
      if found then keys:=array_append(keys,o->>'event_key'); end if;
    end if;
  end loop;
  if cardinality(keys)=0 then return 0; end if;
  select md5(string_agg(k,',' order by k)) into signature from unnest(keys) k;
  insert into public.cme_email_outbox(dedup_key,user_id,forest_id,category,recipient,subject,body_html)
  select 'hotspot/'||p_forest||'/'||signature||'/'||m.user_id,m.user_id,p_forest,'hotspot',u.email,p_subject,p_html
  from public.cme_memberships m join public.cme_notification_preferences p using(user_id) join auth.users u on u.id=m.user_id
  where m.forest_id=p_forest and m.status='approved' and p.events_enabled and u.email_confirmed_at is not null
  on conflict(dedup_key) do nothing;
  get diagnostics queued=row_count;
  if p_line_text is not null then
    insert into public.cme_line_outbox(dedup_key,user_id,forest_id,category,message)
    select 'hotspot/'||p_forest||'/'||signature||'/'||m.user_id,m.user_id,p_forest,'hotspot',p_line_text
    from public.cme_memberships m join public.cme_line_links l using(user_id)
    where m.forest_id=p_forest and m.status='approved'
    on conflict(dedup_key) do nothing;
    get diagnostics extra=row_count;
    queued:=queued+extra;
  end if;
  return queued;
end $$;
revoke all on function public.cme_enqueue_hotspots(text,jsonb,text,text,text) from public,anon,authenticated;
grant execute on function public.cme_enqueue_hotspots(text,jsonb,text,text,text) to service_role;
notify pgrst,'reload schema';
commit;
