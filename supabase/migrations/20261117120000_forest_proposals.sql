-- Community forests that are not in the system yet, proposed by anyone (no account needed).
-- Proposals stay private: only the team (service role) reads them, checks them and adds the
-- forest by hand. The contact phone is for the team only and is never shown on the site.
create table public.cme_forest_proposals (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  name text not null check (char_length(name) between 2 and 120),
  village text not null default '' check (char_length(village) <= 120),
  tambon text not null default '' check (char_length(tambon) <= 80),
  district text not null default '' check (char_length(district) <= 80),
  latitude double precision not null check (latitude between 17 and 21),
  longitude double precision not null check (longitude between 97.3 and 100),
  details text not null default '' check (char_length(details) <= 1000),
  proposer_name text not null default '' check (char_length(proposer_name) <= 80),
  contact_phone text check (contact_phone is null or contact_phone ~ '^[0-9+() -]{6,20}$'),
  ip_hash text not null check (char_length(ip_hash) = 64),
  status text not null default 'pending' check (status in ('pending', 'accepted', 'duplicate', 'rejected')),
  review_note text not null default '' check (char_length(review_note) <= 1000),
  reviewed_at timestamptz
);
create index cme_forest_proposals_recent on public.cme_forest_proposals (ip_hash, created_at desc);
alter table public.cme_forest_proposals enable row level security;
revoke all on public.cme_forest_proposals from public, anon, authenticated;
grant all on public.cme_forest_proposals to service_role;

-- One insert path with limits, so a public form cannot flood the table:
-- at most 10 proposals per sender per hour and 500 in total per day.
create or replace function public.cme_propose_forest(p jsonb, p_ip_hash text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare new_id uuid;
begin
  if (select count(*) from public.cme_forest_proposals where ip_hash = p_ip_hash and created_at > now() - interval '1 hour') >= 10 then
    raise exception 'ส่งข้อเสนอถี่เกินไป กรุณาลองใหม่ภายหลัง' using errcode = '22023';
  end if;
  if (select count(*) from public.cme_forest_proposals where created_at > now() - interval '1 day') >= 500 then
    raise exception 'วันนี้มีข้อเสนอจำนวนมากแล้ว กรุณาลองใหม่พรุ่งนี้' using errcode = '22023';
  end if;
  insert into public.cme_forest_proposals (name, village, tambon, district, latitude, longitude, details, proposer_name, contact_phone, ip_hash)
  values (p->>'name', coalesce(p->>'village', ''), coalesce(p->>'tambon', ''), coalesce(p->>'district', ''),
          (p->>'latitude')::double precision, (p->>'longitude')::double precision, coalesce(p->>'details', ''),
          coalesce(p->>'proposer_name', ''), nullif(p->>'contact_phone', ''), p_ip_hash)
  returning id into new_id;
  return new_id;
end $$;
revoke all on function public.cme_propose_forest(jsonb, text) from public, anon, authenticated;
grant execute on function public.cme_propose_forest(jsonb, text) to service_role;
