-- Fixed public trigger. It can only execute bounded, service-side tasks;
-- it cannot create arbitrary jobs or read admin progress. No credentials here.
begin;
select cron.schedule('chiangmaieyes-archive-worker','* * * * *',
  $job$select net.http_get(
    url := 'https://backend-mocha-tau-49.vercel.app/api/archive/worker',
    timeout_milliseconds := 55000
  );$job$);
commit;
