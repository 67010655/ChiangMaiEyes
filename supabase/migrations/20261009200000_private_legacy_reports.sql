-- Apply only after production switches its legacy UI to the authenticated API.
-- Rows are retained. Rollback grants/policies are in the private pre-release backup.
begin;
revoke all on public.manual_hotspot_reports,public.alert_subscriptions,public.alert_notifications,public.field_activity_reports from public,anon,authenticated;
grant all on public.manual_hotspot_reports,public.alert_subscriptions,public.alert_notifications,public.field_activity_reports to service_role;
notify pgrst,'reload schema';
commit;
