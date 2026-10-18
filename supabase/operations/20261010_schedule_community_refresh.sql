-- Run only on the approved ChiangMaiEyes production project.
-- Uses the existing public dashboard path; no credentials go into pg_net.
-- Re-running cron.schedule with this name updates the existing job.
begin;
create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;
revoke usage on schema cron,net from public,anon,authenticated;
select cron.schedule(
  'chiangmaieyes-community-refresh',
  '*/10 * * * *',
  $job$select net.http_get(
    url := 'https://backend-mocha-tau-49.vercel.app/api/dashboard',
    timeout_milliseconds := 55000
  );$job$
);
commit;

-- Inspect using the database owner, not a public browser endpoint:
-- select jobid,jobname,schedule,active from cron.job
--   where jobname='chiangmaieyes-community-refresh';
-- select status,start_time,end_time from cron.job_run_details
--   where jobid=(select jobid from cron.job where jobname='chiangmaieyes-community-refresh')
--   order by start_time desc limit 5;
-- select status_code,timed_out,error_msg,created from net._http_response
--   order by created desc limit 5;
-- To pause: select cron.alter_job(job_id := <observed jobid>, active := false);
