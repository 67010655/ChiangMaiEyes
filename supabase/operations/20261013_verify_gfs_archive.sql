-- Read-only checks; exposes only scientific archive totals and boolean ACLs.
select jsonb_build_object(
  'frames',(select count(*) from public.cme_gfs_frames),
  'cells_min',(select min(cell_count) from public.cme_gfs_frames),
  'cells_max',(select max(cell_count) from public.cme_gfs_frames),
  'raw_bytes',(select coalesce(sum(octet_length(grib)),0) from public.cme_gfs_frames),
  'invalid_hashes',(select count(*) from public.cme_gfs_frames where id<>encode(sha256(grib),'hex')),
  'first_stored',(select min(first_stored_at) from public.cme_gfs_frames),
  'anon_reads_table',has_table_privilege('anon','public.cme_gfs_frames','SELECT'),
  'member_inserts_table',has_table_privilege('authenticated','public.cme_gfs_frames','INSERT'),
  'anon_ingests',has_function_privilege('anon','public.cme_gfs_ingest(jsonb,text)','EXECUTE'),
  'member_reads_rpc',has_function_privilege('authenticated','public.cme_gfs_read(timestamptz,timestamptz,integer,integer)','EXECUTE'),
  'hourly_jobs',(select count(*) from cron.job where jobname in('chiangmaieyes-gfs-current','chiangmaieyes-gfs-24h','chiangmaieyes-gfs-48h') and active)
) as gfs_archive_checks;
