-- Transactional permission audit. Synthetic actors have no login credentials.
-- The deliberate ZX001 exception rolls back ALL fixture rows and local roles.
-- Only boolean check results survive in a session setting, for the final SELECT.
do $audit$
declare
  a uuid := 'c0de0000-0012-4000-8000-000000000001';
  b uuid := 'c0de0000-0012-4000-8000-000000000002';
  c uuid := 'c0de0000-0012-4000-8000-000000000003';
  incident uuid := 'c0de0000-0012-4000-8000-000000000010';
  checks jsonb := '{}'::jsonb; detail jsonb; denied boolean;
begin
  begin
    if exists(select 1 from auth.users where id in(a,b,c)) or
       exists(select 1 from public.cme_forests where forest_id like '__audit_20261012_%') then
      raise exception 'Audit fixture identity already exists; stop without changing existing data';
    end if;
    insert into auth.users(id,email,email_confirmed_at,raw_user_meta_data)
      values(a,'ux-a@chiangmaieyes.example.invalid',now(),'{"full_name":"Audit A"}'),
            (b,'ux-b@chiangmaieyes.example.invalid',now(),'{"full_name":"Audit B"}'),
            (c,'ux-c@chiangmaieyes.example.invalid',now(),'{"full_name":"Audit C","role":"admin","is_admin":true}');
    insert into public.cme_forests(forest_id,name,amphoe,source)
      values('__audit_20261012_A','Audit fixture A','Audit','Synthetic transactional fixture'),
            ('__audit_20261012_B','Audit fixture B','Audit','Synthetic transactional fixture');
    insert into public.cme_memberships(user_id,forest_id,status)
      values(a,'__audit_20261012_A','approved'),(b,'__audit_20261012_B','approved');
    insert into public.cme_incidents(id,forest_id,created_by,observation,latitude,longitude,observed_at,description,request_hash)
      values(incident,'__audit_20261012_A',a,'smoke',18.8,98.9,now(),'Synthetic audit, rolled back','audit-20261012');

    set local role authenticated;
    perform set_config('request.jwt.claim.sub',a::text,true);
    checks:=checks||jsonb_build_object('owner_reads',public.cme_can_read_incident(incident),
      'owner_manages',public.cme_manages_incident(incident),
      'owner_rls_reads',(select count(*)=1 from public.cme_incidents where id=incident));
    perform set_config('request.jwt.claim.sub',b::text,true);
    checks:=checks||jsonb_build_object('unrelated_forest_denied',not public.cme_can_read_incident(incident),
      'unrelated_rls_hides',(select count(*)=0 from public.cme_incidents where id=incident),
      'client_cannot_claim_mail',not has_function_privilege(current_user,'public.cme_claim_emails(integer)','execute'));
    denied:=false;
    begin
      perform public.cme_action('incident_detail',jsonb_build_object('id',incident));
    exception when insufficient_privilege then denied:=true;
    end;
    checks:=checks||jsonb_build_object('unrelated_rpc_denied',denied);

    reset role;
    insert into public.cme_incident_partners(incident_id,forest_id,invited_by)
      values(incident,'__audit_20261012_B',a);
    set local role authenticated;
    perform set_config('request.jwt.claim.sub',b::text,true);
    detail:=public.cme_action('incident_detail',jsonb_build_object('id',incident));
    checks:=checks||jsonb_build_object('invited_can_read',public.cme_can_read_incident(incident),
      'invited_cannot_manage',not public.cme_manages_incident(incident),
      'invited_cannot_note',not (detail->>'can_note')::boolean);
    perform public.cme_action('respond_partner',jsonb_build_object('id',incident,'forest_id','__audit_20261012_B','status','accepted'));
    detail:=public.cme_action('incident_detail',jsonb_build_object('id',incident));
    checks:=checks||jsonb_build_object('accepted_can_note',(detail->>'can_note')::boolean,
      'accepted_cannot_manage',not public.cme_manages_incident(incident));
    reset role;
    update public.cme_memberships set status='revoked' where user_id=b;
    set local role authenticated;
    perform set_config('request.jwt.claim.sub',b::text,true);
    checks:=checks||jsonb_build_object('revoked_loses_access',not public.cme_can_read_incident(incident));
    perform set_config('request.jwt.claim.sub',c::text,true);
    checks:=checks||jsonb_build_object('metadata_cannot_grant_admin',not public.cme_is_admin(),
      'outsider_denied',not public.cme_can_read_incident(incident));
    reset role;
    set local role anon;
    denied:=false;
    begin
      perform 1 from public.cme_incidents where id=incident;
    exception when insufficient_privilege then denied:=true;
    end;
    checks:=checks||jsonb_build_object('anonymous_private_read_denied',denied,
      'anonymous_cannot_claim_mail',not has_function_privilege(current_user,'public.cme_claim_emails(integer)','execute'));
    if exists(select 1 from jsonb_each(checks) where value <> 'true'::jsonb) then
      raise exception 'Permission audit failed: %',checks;
    end if;
    raise exception 'Rollback synthetic fixtures' using errcode='ZX001';
  exception when sqlstate 'ZX001' then null;
  end;
  perform set_config('cme.permission_audit_result',checks::text,false);
end $audit$;
select current_setting('cme.permission_audit_result',true)::jsonb as checks,
  (select count(*) from auth.users where id in('c0de0000-0012-4000-8000-000000000001','c0de0000-0012-4000-8000-000000000002','c0de0000-0012-4000-8000-000000000003')) as fixture_users_left,
  (select count(*) from public.cme_forests where forest_id like '__audit_20261012_%') as fixture_forests_left,
  (select count(*) from public.cme_incidents where id='c0de0000-0012-4000-8000-000000000010') as fixture_incidents_left;
