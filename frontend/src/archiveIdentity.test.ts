import {PGlite} from '@electric-sql/pglite';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {describe,it,expect} from 'vitest';

describe('archive repair preserves source evidence and fixes summary identity',()=>{
  it('repairs live/backfill duplicates, preserves both rows, and excludes old AQI conversions',async()=>{
    const db=new PGlite();
    try{
      await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
      const base=readFileSync(resolve(__dirname,'../../supabase/migrations/20261010100000_environment_and_research.sql'),'utf8');
      await db.exec(base.split('-- Private, append-only')[0]+'commit;');
      const add=async(id:string,key:string,kind:string,source:string,payload:any,lat:number|null=19.41368,lon:number|null=99.02454)=>{
        await db.query(`insert into public.cme_observations(id,observation_key,kind,observed_at,retrieved_at,source,latitude,longitude,payload)
          values($1,$2,$3,'2026-10-10T06:44:00Z','2026-10-10T10:00:00Z',$4,$5,$6,$7::jsonb)`,[id,key,kind,source,lat,lon,JSON.stringify(payload)]);
      };
      await add('live','legacy-live','hotspot','NASA FIRMS',{id:'HS-018',satellite:'N21'});
      await add('backfill','legacy-backfill','hotspot','VIIRS_NOAA21_SP',{satellite:'NOAA-21'});
      await add('old-aqi','old-aqi','pm25','AQICN',{id:'AQICN-1',pm25:12});
      await add('measured','measured','pm25','Air4Thai PCD',{id:'CM-fixture',pm25:8},null,null);
      await db.exec(readFileSync(resolve(__dirname,'../../supabase/migrations/20261010220000_observation_identity_and_pm_semantics.sql'),'utf8'));
      const original=await db.query<{observation_key:string,payload:any}>('select observation_key,payload from public.cme_observations where kind=\'hotspot\'');
      expect(original.rows).toHaveLength(2);
      expect(new Set(original.rows.map(x=>x.observation_key)).size).toBe(1);
      const expected=createHash('sha256').update('hotspot/v2|noaa21|19.413680|99.024540|2026-10-10T06:44:00.000000+00:00').digest('hex');
      expect(original.rows[0].observation_key).toBe(expected);
      expect((await db.query<{n:number}>('select count(*)::int as n from public.cme_archive_key_repairs')).rows[0].n).toBe(2);
      const read=(kind:string)=>db.query<{value:any}>("select public.cme_archive_read('2026-10-09','2026-10-11',$1,null,0,500) as value",[kind]);
      expect((await read('hotspot')).rows[0].value.total).toBe(1);
      const pm=(await read('pm25')).rows[0].value;
      expect(pm.total).toBe(1);expect(pm.daily[0].pm25_mean).toBe(8);expect(pm.legacy_pm25_excluded).toBe(1);
      expect((await db.query<{n:number}>('select count(*)::int as n from public.cme_observations')).rows[0].n).toBe(4);
      // A request already running in the previous deployment must not restore duplicate counts.
      const run={run_key:'old-client',collected_at:'2026-10-10T11:00:00Z',mode:'scheduled',status:'partial',sources:{},counts:{hotspot:1}};
      const row={id:'old-client-later',observation_key:'wrong-sequence-again',kind:'hotspot',observed_at:'2026-10-10T06:44:00Z',retrieved_at:'2026-10-10T11:00:00Z',source:'NASA FIRMS',latitude:19.41368,longitude:99.02454,forest_ids:[],payload:{id:'HS-001',satellite:'N21'}};
      await db.query('select public.cme_archive_ingest($1::jsonb,$2::jsonb)',[JSON.stringify(run),JSON.stringify([row])]);
      expect((await read('hotspot')).rows[0].value.total).toBe(1);
      await db.exec('set role anon;');
      await expect(db.query('select * from public.cme_archive_key_repairs')).rejects.toThrow();
    }finally{await db.close();}
  },30000);
});
