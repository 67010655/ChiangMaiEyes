begin;
create or replace function public.cme_archive_finish(p_id bigint,p_token uuid,p_result jsonb,p_rows jsonb,p_children jsonb default '[]') returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.cme_archive_tasks%rowtype; state text; run jsonb; saved jsonb; pending integer; failures integer; received_tasks integer;
begin
  select * into t from public.cme_archive_tasks where id=p_id for update;
  if not found or t.status<>'running' or t.lease_token<>p_token or t.lease_until<now() then
    raise exception 'worker lease lost' using errcode='40001'; end if;
  if t.kind='firms' and coalesce(p_result->>'bbox','')<>'98.0086,17.2732,99.5730,20.1474' then
    p_result:=p_result||'{"status":"unavailable","error":"geographic_scope_mismatch"}'::jsonb;
    p_rows:='[]'::jsonb;
  end if;
  state:=p_result->>'status';
  if state is null or state not in ('received','partial','not_available','unavailable') or p_rows is null or jsonb_typeof(p_rows)<>'array'
    or jsonb_typeof(p_children)<>'array' or jsonb_array_length(p_children)>400 then raise exception 'invalid task result' using errcode='22023'; end if;
  if state='unavailable' then
    update public.cme_archive_tasks set status=case when attempts>=3 then 'failed' else 'queued' end,
      available_at=now()+make_interval(secs=>least(300,15*(2^attempts)::integer)),
      lease_until=null,lease_token=null,result=p_result,
      attempt_log=attempt_log||jsonb_build_array(jsonb_build_object('at',now(),'event','upstream_failed','code',p_result->>'error'))
    where id=p_id;
  else
    run:=jsonb_build_object('run_key','task/'||t.id||'/'||t.attempts||'/'||encode(sha256(convert_to(p_token::text,'UTF8')),'hex'),'collected_at',now(),'mode','backfill',
      'status',case when state='received' then 'complete' else 'partial' end,'sources',jsonb_build_array(p_result),'counts',jsonb_build_object(t.kind,jsonb_array_length(p_rows)));
    saved:=public.cme_archive_ingest(run,p_rows);
    insert into public.cme_archive_tasks(job_id,task_key,kind,payload,status,result,finished_at)
    select t.job_id,x.task_key,x.kind,x.payload,coalesce(x.status,'queued'),coalesce(x.result,'{}'),
      case when x.status='not_available' then now() else null end
    from jsonb_to_recordset(p_children) x(task_key text,kind text,payload jsonb,status text,result jsonb)
    on conflict do nothing;
    if t.kind='firms' and p_result->>'sensor' in ('SNPP','NOAA-20','NOAA-21') then
      insert into public.cme_firms_coverage(run_key,sensor,utc_day,source,status,checked_at,invalid_rows,retained_start,retained_end,bbox)
      select run->>'run_key',p_result->>'sensor',(p_result->>'utc_start')::date+g.i,
        p_result->>'source',state,now(),coalesce((p_result->>'invalid_rows')::integer,0),j.start_at,j.end_at,p_result->>'bbox'
      from generate_series(0,(p_result->>'days')::integer-1) g(i),public.cme_archive_jobs j where j.id=t.job_id on conflict do nothing;
    end if;
    update public.cme_archive_tasks set status=state,lease_until=null,lease_token=null,
      received=jsonb_array_length(p_rows),result=p_result,finished_at=now(),
      attempt_log=attempt_log||jsonb_build_array(jsonb_build_object('at',now(),'event',state,'received',jsonb_array_length(p_rows))) where id=p_id;
  end if;
  select count(*) filter(where status in ('queued','running')),
    count(*) filter(where status in ('failed','partial','not_available')),
    count(*) filter(where status in ('received','partial')) into pending,failures,received_tasks
  from public.cme_archive_tasks where job_id=t.job_id;
  update public.cme_archive_jobs set status=case when pending>0 then 'running'
    when failures=0 then 'completed' when received_tasks>0 then 'partial' else 'failed' end where id=t.job_id;
  return jsonb_build_object('saved',saved,'pending',pending);
end $$;
revoke all on function public.cme_archive_finish(bigint,uuid,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.cme_archive_finish(bigint,uuid,jsonb,jsonb,jsonb) to service_role;

update public.cme_archive_tasks t set status='queued',attempts=0,available_at=now(),finished_at=null,
  attempt_log=attempt_log||jsonb_build_array(jsonb_build_object('at',now(),'event','scope_coverage_correction'))
from public.cme_archive_jobs j where t.job_id=j.id and j.request_key like 'geographic-repair/%'
  and t.kind='firms' and t.status in ('received','partial')
  and not exists(select 1 from public.cme_firms_coverage c
    where c.run_key like 'task/'||t.id||'/%' and c.bbox='98.0086,17.2732,99.5730,20.1474');
update public.cme_archive_jobs j set status='queued'
where j.request_key like 'geographic-repair/%' and exists(
  select 1 from public.cme_archive_tasks t where t.job_id=j.id and t.status in ('queued','running'));
commit;
