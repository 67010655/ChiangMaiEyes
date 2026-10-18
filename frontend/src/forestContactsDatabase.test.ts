import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterAll, beforeAll, expect, it } from 'vitest';

const db = new PGlite();
const viewer='10000000-0000-4000-8000-000000000001',approved='10000000-0000-4000-8000-000000000002',pending='10000000-0000-4000-8000-000000000003';
const admin='10000000-0000-4000-8000-000000000004';
async function actor(id: string,role='authenticated'){
  await db.exec(`reset role; set role ${role};`);
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[id]);
}
async function read(name: string,ids=['A','B']){
  return (await db.query<{value:any}>(`select public.${name}($1::text[]) as value`,[ids])).rows[0].value;
}
beforeAll(async()=>{
  await db.exec(`create schema auth; create role anon; create role authenticated; create role service_role;
    create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz,raw_user_meta_data jsonb);
    create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
    grant usage on schema public,auth to anon,authenticated,service_role;
    alter default privileges grant execute on functions to anon,authenticated;
    create table public.cme_forests(forest_id text primary key);
    create table public.cme_memberships(id uuid default gen_random_uuid(),forest_id text,user_id uuid,status text,created_at timestamptz default now());
    create table public.cme_admins(user_id uuid primary key);
    create function public.cme_is_admin() returns boolean language sql stable security definer set search_path='' as $$select exists(select 1 from public.cme_admins where user_id=auth.uid())$$;
    insert into public.cme_forests values('A'),('B');`);
  for(const [id,name] of [[viewer,'Viewer'],[approved,'Approved'],[pending,'Pending'],[admin,'Admin']])await db.query("insert into auth.users values($1,$2,now(),$3::jsonb)",[id,name+'@example.test',JSON.stringify({full_name:name})]);
  await db.query('insert into public.cme_admins values($1)',[admin]);
  await db.query("insert into public.cme_memberships(forest_id,user_id,status) values('A',$1,'approved'),('A',$2,'pending'),('B',$2,'rejected')",[approved,pending]);
  await db.exec(readFileSync(resolve(__dirname,'../../supabase/migrations/20261018150000_forest_coordination_contacts.sql'),'utf8'));
},30000);
afterAll(async()=>{await db.close();});

it('anonymous SQL exposes only forest id and approval presence; private RPC and base tables are denied',async()=>{
  await actor('','anon');
  expect(await read('cme_forest_contact_status')).toEqual([{forest_id:'A',has_representative:true},{forest_id:'B',has_representative:false}]);
  await expect(read('cme_forest_contacts')).rejects.toThrow();
  await expect(db.query('select * from auth.users')).rejects.toThrow();
  await expect(db.query('select * from public.cme_memberships')).rejects.toThrow();
});
it('a confirmed self-service account without approved membership receives the exact 42501 denial',async()=>{
  await actor(viewer);
  await expect(read('cme_forest_contacts')).rejects.toMatchObject({code:'42501',message:'เฉพาะตัวแทนป่าชุมชนที่ได้รับอนุมัติ'});
  await actor(pending);await expect(read('cme_forest_contacts')).rejects.toMatchObject({code:'42501'});
});
it('an approved representative may read neighboring forests; an admin needs no membership',async()=>{
  await actor(approved);
  expect(await read('cme_forest_contacts')).toEqual([{forest_id:'A',representatives:[{name:'Approved',email:'Approved@example.test'}]},{forest_id:'B',representatives:[]}]);
  await expect(read('cme_forest_contacts',['A','B','C','D'])).rejects.toThrow();
  await actor(admin);expect((await read('cme_forest_contacts'))[0].representatives).toHaveLength(1);
});
it('SQL rechecks confirmation even if invoked directly with an authenticated role',async()=>{
  await actor('');await expect(read('cme_forest_contacts')).rejects.toThrow();
  await db.exec('reset role');await db.query('update auth.users set email_confirmed_at=null where id=$1',[approved]);
  await actor(approved);await expect(read('cme_forest_contacts')).rejects.toThrow();
  await db.exec('reset role');await db.query('update auth.users set email_confirmed_at=now() where id=$1',[approved]);
});
it('revoked approval disappears from both public status and private contact results immediately',async()=>{
  await db.exec('reset role');await db.query("update public.cme_memberships set status='revoked' where user_id=$1",[approved]);
  await actor(approved);await expect(read('cme_forest_contacts')).rejects.toMatchObject({code:'42501'});
  await actor(admin);
  expect((await read('cme_forest_contacts'))[0].representatives).toEqual([]);
  await actor('','anon');expect((await read('cme_forest_contact_status'))[0].has_representative).toBe(false);
});
it('an approved membership alone does not expose an unconfirmed account',async()=>{
  await db.exec('reset role');
  await db.query("update public.cme_memberships set status='approved' where user_id=$1",[approved]);
  await db.query('update auth.users set email_confirmed_at=null where id=$1',[approved]);
  await actor(admin);expect((await read('cme_forest_contacts'))[0].representatives).toEqual([]);
  await actor('','anon');expect((await read('cme_forest_contact_status'))[0].has_representative).toBe(false);
});
