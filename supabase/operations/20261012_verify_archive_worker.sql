select
 j.jobid,j.jobname,j.schedule,j.active,
 (select status from cron.job_run_details where jobid=j.jobid order by start_time desc limit 1) as cron_status,
 (select status_code from net._http_response where content like '%"status":"processed"%' order by created desc limit 1) as worker_http,
 (select created from net._http_response where content like '%"status":"processed"%' order by created desc limit 1) as worker_received,
 (select count(*) from public.cme_observations) as original_rows,
 (select count(*) from public.cme_observation_heads) as latest_keys,
 has_function_privilege('anon','public.cme_archive_claim(uuid)','execute') as anon_can_claim,
 has_function_privilege('authenticated','public.cme_archive_job_status(uuid)','execute') as member_can_read_private_jobs,
 has_table_privilege('anon','public.cme_observation_heads','select') as anon_can_read_heads
from cron.job j where j.jobname='chiangmaieyes-archive-worker';
