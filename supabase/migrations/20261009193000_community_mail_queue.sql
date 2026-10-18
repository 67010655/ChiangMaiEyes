begin;
create table if not exists public.cme_hotspot_seen (
  forest_id text not null references public.cme_forests(forest_id), event_key text not null,
  observed_at timestamptz not null, primary key(forest_id,event_key)
);
alter table public.cme_hotspot_seen enable row level security;
revoke all on public.cme_hotspot_seen from public,anon,authenticated;
grant all on public.cme_hotspot_seen to service_role;

-- Persist observations and their messages in one transaction, so a worker
-- failure cannot acknowledge a new observation without recording its alert.
create or replace function public.cme_enqueue_hotspots(p_forest text,p_observations jsonb,p_subject text,p_html text)
returns integer language plpgsql security definer set search_path='' as $$
declare o jsonb; keys text[]:=array[]::text[]; queued integer; signature text;
begin
  if not exists(select 1 from public.cme_memberships m join public.cme_notification_preferences p using(user_id)
    where m.forest_id=p_forest and m.status='approved' and p.events_enabled) then return 0; end if;
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
  return queued;
end $$;
revoke all on function public.cme_enqueue_hotspots(text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.cme_enqueue_hotspots(text,jsonb,text,text) to service_role;

create or replace function public.cme_receive_delivery(p_receipt text,p_provider_id text,p_status text)
returns boolean language plpgsql security definer set search_path='' as $$
declare recipient_id uuid;
begin
  if p_status not in ('delivered','bounced','complained','failed') then return false; end if;
  select user_id into recipient_id from public.cme_email_outbox where provider_id=p_provider_id for update;
  if not found then return false; end if;
  insert into public.cme_webhook_receipts(id) values(p_receipt) on conflict do nothing;
  if not found then return false; end if;
  update public.cme_email_outbox set delivery_status=p_status where provider_id=p_provider_id and coalesce(delivery_status,'') not in ('bounced','complained');
  if p_status in ('bounced','complained') then
    update public.cme_notification_preferences set events_enabled=false,daily_enabled=false,updated_at=now() where user_id=recipient_id;
  end if;
  return true;
end $$;
revoke all on function public.cme_receive_delivery(text,text,text) from public,anon,authenticated;
grant execute on function public.cme_receive_delivery(text,text,text) to service_role;

-- Tighten the function search path on previously applied definitions as well.
do $$ declare f record; begin
  for f in select oid::regprocedure as signature from pg_proc where pronamespace='public'::regnamespace and proname like 'cme_%' and prosecdef loop
    execute format('alter function %s set search_path = %L',f.signature,'');
  end loop;
end $$;
notify pgrst,'reload schema';
commit;
