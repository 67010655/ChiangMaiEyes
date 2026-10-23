import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const mig = (f: string) => readFileSync(resolve(__dirname, '../../supabase/migrations/' + f), 'utf8');
const db = new PGlite();
const admin = '10000000-0000-4000-8000-000000000001';
const alice = '10000000-0000-4000-8000-000000000002'; // approved rep of forest A, reports pins
const bob = '10000000-0000-4000-8000-000000000003'; // approved rep of forest B
const carol = '10000000-0000-4000-8000-000000000004'; // asked for forest B, not approved yet
const dave = '10000000-0000-4000-8000-000000000005'; // signed up, no forest at all
const pin = '20000000-0000-4000-8000-000000000001';
const as = async (uid: string | null, role = 'authenticated') => {
  await db.exec(`reset role; set role ${role};`);
  await db.query(`select set_config('request.jwt.claim.sub',$1,false)`, [uid ?? '']);
};
const action = async (name: string, payload = {}) => (await db.query<{ v: any }>('select public.cme_action($1,$2::jsonb) as v', [name, JSON.stringify(payload)])).rows[0].v;
const pins = async () => (await db.query<{ v: any }>('select public.cme_open_pins() as v')).rows[0].v as any[];
const close = async (id: string, outcome: string, note = '') => (await db.query<{ v: any }>('select public.cme_close_incident($1,$2,$3) as v', [id, outcome, note])).rows[0].v;
const report = (id: string, extra = {}) => ({ id, forest_id: 'pin-A', observation: 'smoke', latitude: 18.8, longitude: 98.9, observed_at: new Date(Date.now() - 36e5).toISOString(), description: 'Fixture pin', ...extra });

describe('incident pins: visible to approved reps, ended only by the reporter or an admin', () => {
  beforeAll(async () => {
    await db.exec(`
      create schema auth; create schema storage;
      create table storage.objects(bucket_id text,name text);
      create role anon; create role authenticated; create role service_role bypassrls;
      create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz,raw_user_meta_data jsonb default '{}');
      create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
      grant usage on schema public,auth to anon,authenticated,service_role;
      alter default privileges grant execute on functions to anon,authenticated;
      create table public.manual_hotspot_reports(id uuid primary key,reporter_id uuid,latitude double precision,longitude double precision,amphoe text,tambon text,description text,reported_at timestamptz);
      grant all on all tables in schema public to anon,authenticated;
    `);
    for (const [id, name] of [[admin, 'Admin'], [alice, 'Alice'], [bob, 'Bob'], [carol, 'Carol'], [dave, 'Dave']]) {
      await db.query(`insert into auth.users values($1,$2,now(),$3::jsonb)`, [id, `${name}@example.test`, JSON.stringify({ full_name: name })]);
    }
    await db.exec(mig('20261009190000_community_coordination.sql'));
    await db.exec(mig('20261009195000_evidence_and_mail_claim.sql'));
    await db.exec(mig('20261023100000_incident_pins.sql'));
    await db.exec(`insert into public.cme_forests(forest_id,name,amphoe) values('pin-A','Forest A','X'),('pin-B','Forest B','X');
      insert into public.cme_admins(user_id) values('${admin}');
      insert into public.cme_memberships(user_id,forest_id,status) values('${alice}','pin-A','approved'),('${bob}','pin-B','approved'),('${carol}','pin-B','pending');`);
  }, 30000);
  afterAll(async () => { await db.close(); });

  it('a rep of another forest sees the pin with the fixed fields only, and cannot open the incident', async () => {
    await as(alice);
    await action('create_incident', report(pin));
    await as(bob);
    const list = await pins();
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({ id: pin, forest_name: 'Forest A', reporter_name: 'Alice', mine: false, can_close: false, can_open: false, observation: 'smoke' });
    expect(Object.keys(list[0]).sort()).toEqual(['amphoe', 'can_close', 'can_open', 'contact_phone', 'created_at', 'description', 'expires_at', 'forest_id', 'forest_name', 'id', 'latitude', 'longitude', 'mine', 'nearby', 'observation', 'observed_at', 'reporter_name', 'status']);
    // The widening is only the pin list: the incident itself stays private to its forest.
    expect(await action('list_incidents')).toEqual([]);
    expect((await db.query('select * from public.cme_incidents')).rows).toEqual([]);
    await expect(action('incident_detail', { id: pin })).rejects.toThrow();
  });

  it('anonymous, unapproved and forest-less users get nothing', async () => {
    for (const uid of [carol, dave]) { await as(uid); await expect(pins()).rejects.toThrow(); }
    await as(null, 'anon');
    await expect(pins()).rejects.toThrow();
  });

  it('an admin sees every pin and the reporter can close their own', async () => {
    await as(admin);
    expect((await pins())[0]).toMatchObject({ can_close: true, can_open: true });
    await as(alice);
    expect((await pins())[0]).toMatchObject({ mine: true, can_close: true, can_open: true });
  });

  it('only the reporter or an admin can end a pin, and only once', async () => {
    await as(bob);
    await expect(close(pin, 'closed')).rejects.toThrow(/เฉพาะคนที่แจ้งเหตุ/);
    await as(alice);
    const ended = await close(pin, 'closed', 'ดับแล้ว');
    expect(ended.status).toBe('closed');
    await expect(close(pin, 'closed')).rejects.toThrow();
    await as(bob);
    expect(await pins()).toEqual([]);
    await as(alice);
    const detail = await action('incident_detail', { id: pin });
    expect(detail.events.map((e: any) => [e.kind, e.status_to, e.note])).toContainEqual(['status', 'closed', 'ดับแล้ว']);
  });

  it('"not a fire" also removes the pin, and an admin may end someone else\'s pin', async () => {
    const second = '20000000-0000-4000-8000-000000000002';
    await as(alice); await action('create_incident', report(second));
    await as(admin);
    expect((await close(second, 'cancelled')).status).toBe('cancelled');
    await as(bob);
    expect(await pins()).toEqual([]);
    await as(alice);
    await expect(close(second, 'bad' as any)).rejects.toThrow();
  });

  it('the reporter alone sets an optional phone, and other reps see it in the pin', async () => {
    const third = '20000000-0000-4000-8000-000000000003';
    await as(alice); await action('create_incident', report(third));
    const setPhone = async (id: string, phone: string | null) => (await db.query('select public.cme_set_incident_contact($1,$2)', [id, phone])).rows;
    await setPhone(third, '081-234-5678');
    await expect(setPhone(third, 'call me maybe')).rejects.toThrow();
    await as(bob);
    expect((await pins())[0].contact_phone).toBe('081-234-5678');
    await expect(setPhone(third, '0999999999')).rejects.toThrow();
    await as(alice); await setPhone(third, null);
    await as(bob);
    expect((await pins())[0].contact_phone).toBeNull();
  });

  it('allows 3 new pins per person per day, then asks them to call 1362', async () => {
    await as(bob);
    for (const n of [4, 5, 6]) await action('create_incident', report(`20000000-0000-4000-8000-00000000000${n}`, { forest_id: 'pin-B' }));
    await expect(action('create_incident', report('20000000-0000-4000-8000-000000000007', { forest_id: 'pin-B' }))).rejects.toThrow(/ไม่เกิน 3 ครั้ง/);
  });

  it('closes pins after 3 days from the worker only, and writes the history row itself', async () => {
    await as(admin, 'service_role');
    await db.exec(`update public.cme_incidents set created_at=now()-interval '3 days 1 hour' where id='20000000-0000-4000-8000-000000000004'`);
    const expired = (await db.query<{ v: any }>('select public.cme_expire_incidents() as v')).rows[0].v;
    expect(expired).toHaveLength(1);
    expect(expired[0]).toMatchObject({ id: '20000000-0000-4000-8000-000000000004', forest_id: 'pin-B', created_by: bob });
    const events = (await db.query<{ kind: string; actor_name: string; status_to: string }>(`select kind,actor_name,status_to from public.cme_incident_events where incident_id='20000000-0000-4000-8000-000000000004' order by created_at`)).rows;
    expect(events.at(-1)).toEqual({ kind: 'expired', actor_name: 'ระบบอัตโนมัติ', status_to: 'closed' });
    await as(alice);
    expect((await pins()).map((p: any) => p.id)).not.toContain('20000000-0000-4000-8000-000000000004');
    await as(bob);
    await expect(db.query('select public.cme_expire_incidents()')).rejects.toThrow();
  });

  it('hides pins older than 3 days even before the worker runs', async () => {
    await as(admin, 'service_role');
    await db.exec(`update public.cme_incidents set created_at=now()-interval '4 days' where id='20000000-0000-4000-8000-000000000005'`);
    await as(alice);
    expect((await pins()).map((p: any) => p.id)).not.toContain('20000000-0000-4000-8000-000000000005');
  });
});
