begin;
alter table public.cme_job_runs add column if not exists source text not null default 'dashboard';
alter table public.cme_job_runs add column if not exists run_status text not null default 'running';
alter table public.cme_job_runs add column if not exists lease_until timestamptz default now()+interval '2 minutes';
alter table public.cme_job_runs add column if not exists summary jsonb;
alter table public.cme_job_runs add column if not exists last_error text;
update public.cme_job_runs set run_status='completed',lease_until=null where completed_at is not null;
create index if not exists cme_job_runs_started_at on public.cme_job_runs(started_at desc);

-- A failed or interrupted attempt can be retried in the same interval.
-- Claiming remains available only to the existing backend service role.
create or replace function public.cme_claim_job(p_key text,p_source text)
returns boolean language plpgsql security definer set search_path='' as $$
declare claimed integer;
begin
  if p_key !~ '^community/[0-9]+$' or p_source not in ('dashboard','manual','scheduled') then
    raise exception 'Invalid job metadata' using errcode='22023';
  end if;
  insert into public.cme_job_runs(job_key,source,run_status,lease_until)
    values(p_key,p_source,'running',now()+interval '2 minutes')
  on conflict(job_key) do update set source=excluded.source,run_status='running',
    lease_until=excluded.lease_until,last_error=null
  where public.cme_job_runs.completed_at is null and
    (public.cme_job_runs.run_status='failed' or public.cme_job_runs.lease_until<now());
  get diagnostics claimed=row_count;
  return claimed=1;
end $$;
revoke all on function public.cme_claim_job(text,text) from public,anon,authenticated;
grant execute on function public.cme_claim_job(text,text) to service_role;
notify pgrst,'reload schema';
commit;
