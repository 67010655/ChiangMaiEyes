import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const sql = readFileSync(resolve(__dirname, '../../supabase/migrations/20261009190000_community_coordination.sql'), 'utf8');
const cutover = readFileSync(resolve(__dirname, '../../supabase/migrations/20261009200000_private_legacy_reports.sql'), 'utf8');
const mailSql = readFileSync(resolve(__dirname, '../../supabase/migrations/20261009193000_community_mail_queue.sql'), 'utf8');
const evidenceSql = readFileSync(resolve(__dirname, '../../supabase/migrations/20261009195000_evidence_and_mail_claim.sql'), 'utf8');
const jobSql = readFileSync(resolve(__dirname, '../../supabase/migrations/20261010020000_community_job_observability.sql'), 'utf8');
const practiceSql = readFileSync(resolve(__dirname, '../../supabase/migrations/20261010030000_practice_and_field_checks.sql'), 'utf8');
const archiveSql = readFileSync(resolve(__dirname, '../../supabase/migrations/20261010100000_environment_and_research.sql'), 'utf8');
const db = new PGlite();
const owner = '10000000-0000-4000-8000-000000000001';
const alice = '10000000-0000-4000-8000-000000000002';
const bob = '10000000-0000-4000-8000-000000000003';
const outsider = '10000000-0000-4000-8000-000000000004';
const incident = '20000000-0000-4000-8000-000000000001';
async function actor(uid: string, role = 'authenticated') {
  await db.exec(`reset role; set role ${role};`);
  await db.query(`select set_config('request.jwt.claim.sub',$1,false)`, [uid]);
}
async function action(name: string, payload = {}) {
  const result = await db.query<{ value: any }>('select public.cme_action($1,$2::jsonb) as value', [name, JSON.stringify(payload)]);
  return result.rows[0].value;
}
const report = { id: incident, forest_id: 'test-A', observation: 'smoke', latitude: 18.8, longitude: 98.9, observed_at: '2026-01-01T10:00:00+07:00', description: 'Fixture only' };

describe('community database permissions and transactional workflow', () => {
  beforeAll(async () => {
    await db.exec(`
      create schema auth;
      create schema storage;
      create table storage.objects(bucket_id text,name text);
      create role anon;
      create role authenticated;
      create role service_role bypassrls;
      create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz,raw_user_meta_data jsonb default '{}');
      create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
      grant usage on schema public,auth to anon,authenticated,service_role;
      alter default privileges grant execute on functions to anon,authenticated;
      create table public.manual_hotspot_reports(id uuid primary key,reporter_id uuid,latitude double precision,longitude double precision,amphoe text,tambon text,description text,reported_at timestamptz);
      create table public.alert_subscriptions(id uuid);
      create table public.alert_notifications(id uuid);
      create table public.field_activity_reports(id uuid);
      grant all on all tables in schema public to anon,authenticated;
    `);
    for (const [id, name] of [[owner, 'Owner'], [alice, 'Alice'], [bob, 'Bob'], [outsider, 'Outsider']]) {
      await db.query(`insert into auth.users values($1,$2,now(),$3::jsonb)`, [id, `${name}@example.test`, JSON.stringify({ full_name: name })]);
    }
    await db.exec(sql);
    await db.exec(mailSql);
    await db.exec(evidenceSql);
    await db.exec(cutover);
    await db.exec(jobSql);
    await db.exec(practiceSql);
    await db.exec(archiveSql);
    await db.exec(`insert into public.cme_forests(forest_id,name,amphoe) values('test-A','Fixture A','Fixture'),('test-B','Fixture B','Fixture');`);
    await db.query('insert into public.cme_admins(user_id) values($1)', [owner]);
  }, 30000);
  afterAll(async () => { await db.close(); });

  it('runs the production audit operation without retaining actors, forests or incidents',async()=>{
    await db.exec('reset role');
    const audit=readFileSync(resolve(__dirname,'../../supabase/operations/20261012_audit_community_permissions.sql'),'utf8');
    const outputs=await db.exec(audit);
    const row=outputs[outputs.length-1].rows[0] as any;
    expect(Object.values(row.checks).every(v=>v===true)).toBe(true);
    expect(Object.keys(row.checks)).toHaveLength(17);
    expect([row.fixture_users_left,row.fixture_forests_left,row.fixture_incidents_left]).toEqual([0,0,0]);
  });

  it('denies anonymous access and privileged direct inserts', async () => {
    await actor('', 'anon');
    await expect(action('me')).rejects.toThrow();
    await expect(db.query('select * from public.cme_incidents')).rejects.toThrow();
    await expect(db.query('select public.cme_event($1,$2)', [incident, 'forged'])).rejects.toThrow();
    await expect(db.query('select * from public.manual_hotspot_reports')).rejects.toThrow();
    await actor(alice);
    await expect(db.query('insert into public.cme_admins(user_id) values($1)', [alice])).rejects.toThrow();
    await expect(db.query(`insert into public.cme_memberships(user_id,forest_id,status) values($1,'test-A','approved')`, [alice])).rejects.toThrow();
  });
  it('requires admin approval and rejects a user reviewing their own request', async () => {
    await actor(alice);
    const membership = await action('request_membership', { forest_id: 'test-A', note: 'Fixture request' });
    expect(membership.status).toBe('pending');
    await expect(action('create_incident', report)).rejects.toThrow();
    await expect(action('review_membership', { id: membership.id, status: 'approved' })).rejects.toThrow();
    await actor(owner);
    expect((await action('review_membership', { id: membership.id, status: 'approved' })).status).toBe('approved');
    await actor(bob);
    const other = await action('request_membership', { forest_id: 'test-B' });
    await actor(owner);
    await action('review_membership', { id: other.id, status: 'approved' });
  });
  it('creates one incident and one audit event across retries', async () => {
    await actor(alice);
    expect((await action('create_incident', report)).status).toBe('pending');
    await action('create_incident', report);
    await expect(action('create_incident', { ...report, description: 'Different payload' })).rejects.toThrow();
    const detail = await action('incident_detail', { id: incident });
    expect(detail.events).toHaveLength(1);
    expect(detail.events[0].actor_name).toBe('Alice');
    expect((await action('list_incidents', { forest_id: 'test-A' })).length).toBe(1);
  });
  it('isolates unrelated forests, including direct REST-table reads', async () => {
    await actor(bob);
    expect(await action('list_incidents')).toEqual([]);
    expect((await db.query('select * from public.cme_incidents')).rows).toEqual([]);
    await expect(action('incident_detail', { id: incident })).rejects.toThrow();
  });
  it('checks transitions, reasons and optimistic versions atomically', async () => {
    await actor(alice);
    await expect(action('change_status', { id: incident, version: 1, status: 'closed', note: 'Invalid skip' })).rejects.toThrow();
    await expect(action('change_status', { id: incident, version: 1, status: 'confirmed' })).rejects.toThrow();
    const updated = await action('change_status', { id: incident, version: 1, status: 'confirmed', note: 'Field checked' });
    expect(updated.version).toBe(2);
    await expect(action('change_status', { id: incident, version: 1, status: 'controlled', note: 'Stale write' })).rejects.toThrow();
    expect((await action('incident_detail', { id: incident })).events).toHaveLength(2);
  });
  it('supports a second community accepting an invitation without gaining control', async () => {
    await actor(alice);
    await action('invite_partner', { id: incident, version: 2, forest_id: 'test-B', note: 'Please coordinate' });
    await actor(bob);
    const detail = await action('incident_detail', { id: incident });
    expect(detail.can_manage).toBe(false);
    expect(detail.can_note).toBe(false);
    await expect(action('add_note', { id: incident, note: 'Before acceptance' })).rejects.toThrow();
    await action('respond_partner', { id: incident, forest_id: 'test-B', status: 'accepted' });
    expect((await action('incident_detail', { id: incident })).can_note).toBe(true);
    await action('add_note', { id: incident, note: 'Support accepted' });
    await expect(action('change_status', { id: incident, version: 5, status: 'controlled', note: 'Other forest' })).rejects.toThrow();
    await actor(outsider);
    await expect(action('incident_detail', { id: incident })).rejects.toThrow();
  });
  it('publishes only a deliberately approved coarse summary', async () => {
    await actor(alice);
    const before = await action('incident_detail', { id: incident });
    await action('publish_summary', { id: incident, version: before.incident.version, published: true });
    await actor('', 'anon');
    const result = await db.query<{ value: any }>('select public.cme_public_incidents() as value');
    expect(result.rows[0].value).toHaveLength(1);
    expect(result.rows[0].value[0]).not.toHaveProperty('latitude');
    expect(result.rows[0].value[0]).not.toHaveProperty('created_by');
    expect(result.rows[0].value[0]).not.toHaveProperty('description');
  });
  it('revoking membership immediately removes incident access', async () => {
    await actor(owner);
    const membership = (await action('review_queue')).find((m: any) => m.user_id === bob);
    await action('review_membership', { id: membership.id, status: 'revoked' });
    await actor(bob);
    await expect(action('incident_detail', { id: incident })).rejects.toThrow();
  });
  it('validates opt-in preferences and isolates another user’s preferences', async () => {
    await actor(alice);
    await expect(action('preferences', { quiet_start: 99 })).rejects.toThrow();
    await action('preferences', { events_enabled: true, daily_enabled: false, quiet_enabled: true });
    expect((await action('me')).preferences.events_enabled).toBe(true);
    await actor(bob);
    expect((await db.query('select * from public.cme_notification_preferences')).rows).toEqual([]);
  });
  it('leases a queued email once and forbids client consumption', async () => {
    await db.exec('reset role');
    await db.query(`insert into public.cme_email_outbox(dedup_key,user_id,category,recipient,subject,body_html) values('test-email',$1,'test','fixture@example.test','Test','Test')`, [owner]);
    await actor(alice);
    await expect(db.query('select * from public.cme_claim_emails(10)')).rejects.toThrow();
    await actor('', 'service_role');
    expect((await db.query('select * from public.cme_claim_emails(10)')).rows).toHaveLength(1);
    expect((await db.query('select * from public.cme_claim_emails(10)')).rows).toHaveLength(0);
  });
  it('enqueues a new satellite observation once and ignores old/future observations', async () => {
    const rows = [{ event_key: 'fresh', observed_at: new Date().toISOString() },
      { event_key: 'old', observed_at: '2020-01-01T00:00:00Z' },
      { event_key: 'future', observed_at: '2099-01-01T00:00:00Z' }];
    const result = await db.query<{ n: number }>('select public.cme_enqueue_hotspots($1,$2::jsonb,$3,$4) as n', ['test-A', JSON.stringify(rows), 'Fixture', 'Fixture']);
    expect(result.rows[0].n).toBe(1);
    const again = await db.query<{ n: number }>('select public.cme_enqueue_hotspots($1,$2::jsonb,$3,$4) as n', ['test-A', JSON.stringify(rows), 'Fixture', 'Fixture']);
    expect(again.rows[0].n).toBe(0);
    expect((await db.query('select * from public.cme_hotspot_seen')).rows).toHaveLength(1);
  });
  it('deduplicates delivery callbacks and suppresses opt-in after a bounce', async () => {
    await db.query(`update public.cme_email_outbox set provider_id='provider-fixture' where dedup_key like 'hotspot/%'`);
    expect((await db.query<{ ok: boolean }>("select public.cme_receive_delivery('message-fixture','provider-fixture','bounced') as ok")).rows[0].ok).toBe(true);
    expect((await db.query<{ ok: boolean }>("select public.cme_receive_delivery('message-fixture','provider-fixture','bounced') as ok")).rows[0].ok).toBe(false);
    expect((await db.query<{ events_enabled: boolean }>('select events_enabled from public.cme_notification_preferences')).rows[0].events_enabled).toBe(false);
  });
  it('keeps photos private and checks rights and uploaded objects before metadata writes', async () => {
    const photo='30000000-0000-4000-8000-000000000001';
    await actor(alice);
    await expect(db.query('select public.cme_add_photo($1,$2)',[incident,photo])).rejects.toThrow();
    await db.exec('reset role');
    await db.query('insert into storage.objects values($1,$2)',['cme-incident-evidence',incident+'/'+photo+'.jpg']);
    await actor(alice);
    await db.query('select public.cme_add_photo($1,$2)',[incident,photo]);
    expect((await action('incident_detail',{id:incident})).photos).toHaveLength(1);
    await actor(bob);
    expect((await db.query('select * from public.cme_incident_photos')).rows).toHaveLength(0);
    await expect(db.query('select public.cme_add_photo($1,$2)',[incident,photo])).rejects.toThrow();
    await actor('','anon');
    await expect(db.query('select * from public.cme_incident_photos')).rejects.toThrow();
  });
  it('limits worker claims to the backend and allows failed or expired attempts to recover',async()=>{
    await actor('', 'anon');
    await expect(db.query("select public.cme_claim_job('community/1','manual')")).rejects.toThrow();
    await actor(alice);
    await expect(db.query("select public.cme_claim_job('community/1','manual')")).rejects.toThrow();
    await actor('', 'service_role');
    const claim=async()=> (await db.query<{ok:boolean}>("select public.cme_claim_job('community/1','manual') as ok")).rows[0].ok;
    expect(await claim()).toBe(true);expect(await claim()).toBe(false);
    await db.query("update public.cme_job_runs set run_status='failed',lease_until=null where job_key='community/1'");
    expect(await claim()).toBe(true);
    await db.query("update public.cme_job_runs set lease_until=now()-interval '1 minute' where job_key='community/1'");
    expect(await claim()).toBe(true);
    await db.query("update public.cme_job_runs set completed_at=now(),run_status='completed' where job_key='community/1'");
    expect(await claim()).toBe(false);
  });
  it('links duplicate pending reports with preserved histories and rejects cycles', async () => {
    const duplicate='20000000-0000-4000-8000-000000000002';
    await actor(alice);
    await action('create_incident',{...report,id:duplicate});
    await expect(action('merge_incident',{id:duplicate,target_id:duplicate,version:1,note:'Same'})).rejects.toThrow();
    const merged=await action('merge_incident',{id:duplicate,target_id:incident,version:1,note:'Same observation checked'});
    expect(merged.status).toBe('cancelled');expect(merged.linked_incident_id).toBe(incident);
    expect((await action('incident_detail',{id:duplicate})).events).toHaveLength(2);
    await expect(action('change_status',{id:duplicate,version:2,status:'pending',note:'Reopen cycle'})).rejects.toThrow();
    expect((await action('list_incidents',{offset:1}))).toHaveLength(1);
    expect((await action('incident_events',{id:duplicate,offset:1}))).toHaveLength(1);
  });
  it('isolates practice owners and refuses direct or anonymous writes',async()=>{
    const id='40000000-0000-4000-8000-000000000001';
    const data={mode:'practice',title:'Fixture',scenario:'smoke',incidents:[],events:[],feedback:[]};
    await actor(alice);
    const save=(version:number,d:any)=>db.query<{value:any}>('select public.cme_practice_save($1,$2,$3::jsonb) as value',[id,version,JSON.stringify(d)]);
    expect((await save(0,data)).rows[0].value.version).toBe(1);
    expect((await save(0,data)).rows[0].value.version).toBe(1);
    await expect(db.query('update public.cme_practice_runs set version=99')).rejects.toThrow();
    await save(1,{...data,title:'Changed'});
    await expect(save(1,{...data,title:'Stale'})).rejects.toThrow();
    await actor(outsider);
    expect((await db.query('select * from public.cme_practice_runs')).rows).toEqual([]);
    await expect(db.query('select public.cme_practice_read($1)',[id])).rejects.toThrow();
    await expect(save(0,data)).rejects.toThrow();
    await actor('','anon');
    await expect(save(0,data)).rejects.toThrow();
  });
  it('keeps field observations immutable, retry-safe, and private after revocation',async()=>{
    const id='50000000-0000-4000-8000-000000000001', correction='50000000-0000-4000-8000-000000000002';
    const data={outcome:'unverified',method:'unavailable',satellite_match:'not_checked',checked_at:new Date().toISOString(),note:'Fixture evidence unavailable'};
    const save=(cid:string,d:any)=>db.query<{value:any}>('select public.cme_field_check($1,$2,$3::jsonb) as value',[incident,cid,JSON.stringify(d)]);
    await actor(alice);
    await save(id,data);await save(id,data);
    expect((await db.query('select * from public.cme_field_checks')).rows).toHaveLength(1);
    await expect(save(id,{...data,note:'Different evidence'})).rejects.toThrow();
    await expect(db.query('update public.cme_field_checks set data=$1',[data])).rejects.toThrow();
    await save(correction,{...data,corrects_id:id,note:'Fixture correction, old row preserved'});
    expect((await db.query('select * from public.cme_field_checks')).rows).toHaveLength(2);
    await expect(save('50000000-0000-4000-8000-000000000003',{...data,outcome:'fire_found'})).rejects.toThrow();
    await actor(bob); // Membership B was revoked in the earlier workflow.
    expect((await db.query('select * from public.cme_field_checks')).rows).toEqual([]);
    await expect(save('50000000-0000-4000-8000-000000000004',data)).rejects.toThrow();
    await actor('','anon');await expect(db.query('select * from public.cme_field_checks')).rejects.toThrow();
  });
  it('stores archive revisions idempotently and restricts archive access to the backend',async()=>{
    const start='2026-10-09T00:00:00+00:00', end='2026-10-11T00:00:00+00:00';
    const run=(key:string,at:string)=>({run_key:key,collected_at:at,mode:'scheduled',status:'complete',sources:{pm25:{source:'Fixture sensor',available:true}},counts:{pm25:1}});
    const row=(id:string,retrieved:string,value:number)=>({id,observation_key:'sensor-1/2026-10-10T10:00:00Z',kind:'pm25',observed_at:'2026-10-10T10:00:00+00:00',retrieved_at:retrieved,source:'Fixture sensor',latitude:null,longitude:null,forest_ids:[],payload:{pm25:value}});
    await actor('','anon');
    await expect(db.query('select * from public.cme_observations')).rejects.toThrow();
    await expect(db.query("select public.cme_archive_read($1,$2,'pm25',null,0,500)",[start,end])).rejects.toThrow();
    await actor('', 'service_role');
    const ingest=async(r:any,rows:any[])=> (await db.query<{value:any}>(
      'select public.cme_archive_ingest($1::jsonb,$2::jsonb) as value',[JSON.stringify(r),JSON.stringify(rows)])).rows[0].value;
    expect((await ingest(run('archive/1','2026-10-10T10:01:00Z'),[row('row-1','2026-10-10T10:01:00Z',11)])).inserted).toBe(1);
    expect((await ingest(run('archive/1','2026-10-10T10:01:00Z'),[row('row-1','2026-10-10T10:01:00Z',11)])).already_collected).toBe(true);
    await ingest(run('archive/2','2026-10-10T10:11:00Z'),[row('row-2','2026-10-10T10:11:00Z',15)]);
    const read=await db.query<{value:any}>(
      "select public.cme_archive_read($1,$2,'pm25',null,0,500) as value",[start,end]);
    expect(read.rows[0].value.total).toBe(1);
    expect(read.rows[0].value.rows[0].payload.pm25).toBe(15);
    expect(read.rows[0].value.daily[0].pm25_mean).toBe(15);
  });
  it('stores private research records only through an authorized member/admin function',async()=>{
    const id='60000000-0000-4000-8000-000000000001';
    const payload={version:'baseline-v1',accuracy_status:'exploratory'};
    await actor('', 'anon');
    await expect(db.query('select * from public.cme_research_records')).rejects.toThrow();
    await expect(db.query('select public.cme_research_save($1,$2,$3,$4::jsonb,null)',[id,'test-A','model',JSON.stringify(payload)])).rejects.toThrow();
    await actor(owner);
    const save=async(data:any)=>db.query<{value:any}>(
      'select public.cme_research_save($1,$2,$3,$4::jsonb,null) as value',[id,'test-A','model',JSON.stringify(data)]);
    expect((await save(payload)).rows[0].value.kind).toBe('model');
    expect((await save(payload)).rows[0].value.id).toBe(id);
    await expect(save({...payload,accuracy_status:'validated'})).rejects.toThrow();
    expect((await db.query<{n:number}>('select count(*)::int as n from public.cme_research_records')).rows[0].n).toBe(1);
    await expect(db.query("update public.cme_research_records set data='{}'::jsonb")).rejects.toThrow();
  });
});
