-- Fixed NOAA model reads. No credentials, custom URLs or user payloads.
begin;
select cron.schedule('chiangmaieyes-gfs-current','15 * * * *',
  $job$select net.http_get(url := 'https://backend-mocha-tau-49.vercel.app/api/ventilation?lead_hours=0',timeout_milliseconds := 55000);$job$);
select cron.schedule('chiangmaieyes-gfs-24h','20 * * * *',
  $job$select net.http_get(url := 'https://backend-mocha-tau-49.vercel.app/api/ventilation?lead_hours=24',timeout_milliseconds := 55000);$job$);
select cron.schedule('chiangmaieyes-gfs-48h','25 * * * *',
  $job$select net.http_get(url := 'https://backend-mocha-tau-49.vercel.app/api/ventilation?lead_hours=48',timeout_milliseconds := 55000);$job$);
commit;
