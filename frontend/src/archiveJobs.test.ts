import {PGlite} from '@electric-sql/pglite';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {describe,it,expect} from 'vitest';

const migration=(name:string)=>readFileSync(resolve(__dirname,'../../supabase/migrations/'+name),'utf8');
async function fixture(){
  const db=new PGlite();
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
  await db.exec(migration('20261010100000_environment_and_research.sql').split('-- Private, append-only')[0]+'commit;');
  await db.exec(migration('20261010220000_observation_identity_and_pm_semantics.sql'));
  await db.exec(migration('20261012120000_archive_jobs_and_analytics.sql'));
  await db.exec(migration('20261012123000_archive_spatial_summary.sql'));
  await db.exec(migration('20261012140000_firms_geographic_scope.sql'));
  await db.exec(migration('20261020160000_archive_district_filter.sql'));
  await db.exec(migration('20261024090000_archive_analytics_daily_by_date.sql'));
  return db;
}
describe('durable archive jobs and one-window analytics',()=>{
  it('retries a worker from the old deployment instead of accepting the cropped geographic scope',async()=>{
    const db=await fixture();
    try{
      const job={id:'00000000-0000-0000-0000-000000000002',request_key:'scope',start_at:'2026-10-01T00:00:00Z',end_at:'2026-10-02T00:00:00Z'};
      await db.query('select cme_archive_enqueue($1,$2)',[JSON.stringify(job),JSON.stringify([{task_key:'firms',kind:'firms',payload:{}}])]);
      const token='00000000-0000-0000-0000-000000000010';
      const t=(await db.query<{v:any}>('select cme_archive_claim($1) v',[token])).rows[0].v;
      await db.query('select cme_archive_finish($1,$2,$3,$4,$5)',[t.id,token,'{"status":"received","bbox":"97.25,17.35,99.68,20.28"}','[]','[]']);
      const state=(await db.query<{v:any}>('select cme_archive_job_status(null) v')).rows[0].v[0];
      expect(state.detail[0].status).toBe('queued');
      expect(state.detail[0].result.error).toBe('geographic_scope_mismatch');
    }finally{await db.close();}
  },30000);
  it('keeps revisions, supports as-of replay, separates measured/model PM and never invents zero for gaps',async()=>{
    const db=await fixture();
    try{
      const add=async(id:string,kind:string,payload:any,received:string,source='VIIRS_SNPP_NRT')=>{
        await db.query(`insert into public.cme_observations(id,observation_key,kind,observed_at,retrieved_at,source,latitude,longitude,payload)
        values($1,$2,$3,'2026-10-10T06:00:00Z',$4,$5,19,99,$6)`,[id,kind==='hotspot'?'hs':id,kind,received,source,JSON.stringify(payload)]);
      };
      await add('hs1','hotspot',{satellite:'N',confidence:'n',frp:12,district:'เมือง'},'2026-10-10T07:00:00Z');
      await add('hs2','hotspot',{satellite:'N',confidence:'h',frp:42,district:'เมือง'},'2026-10-11T07:00:00Z');
      await add('measured','pm25',{id:'CM-1',measurement_kind:'measured',pm25:8},'2026-10-10T07:00:00Z','Air4Thai');
      await add('model','pm25',{id:'CAMS-grid',measurement_kind:'model',pm25:88},'2026-10-10T07:00:00Z','Open-Meteo CAMS');
      await add('legacy','pm25',{id:'AQI-1',pm25:200},'2026-10-10T07:00:00Z','AQICN');
      const read=async(asof:string|null=null)=>(await db.query<{v:any}>(`select cme_archive_analytics('2026-10-09T17:00:00Z','2026-10-12T00:00:00Z',$1,null) v`,[asof])).rows[0].v;
      const latest=await read();
      expect(latest.total).toBe(1);expect(latest.frp.max).toBe(42);expect(latest.confidence.high).toBe(1);
      expect(latest.hotspots.map((d:any)=>d.count)).toEqual([1,null,null]);
      expect(latest.hotspots[2].partial_day).toBe(true);
      expect(latest.pm25.map((d:any)=>[d.measurement_kind,d.value])).toEqual([['measured',8],['model',88]]);
      const past=await read('2026-10-10T08:00:00Z');expect(past.frp.max).toBe(12);expect(past.confidence.nominal).toBe(1);
      await db.exec("update cme_observations set forest_ids=array['forest-a'] where id='hs1'; update cme_observations set forest_ids=array['forest-b'] where id='hs2';");
      const scoped=await db.query<{v:any}>("select cme_archive_analytics('2026-10-09T17:00:00Z','2026-10-12T00:00:00Z','2026-10-11T08:00:00Z','forest-a') v");
      expect(scoped.rows[0].v.total).toBe(0); // Latest revision changed its spatial assignment.
      expect((await db.query<{n:number}>('select count(*)::int n from cme_observations')).rows[0].n).toBe(5);
      await db.exec(`insert into cme_firms_coverage select 'fixture',s,d,'fixture','received','2026-10-12T10:00:00Z',0,'2026-10-09T17:00:00Z','2026-10-12T00:00:00Z','98.0086,17.2732,99.5730,20.1474'
        from (values('SNPP'),('NOAA-20'),('NOAA-21')) sensors(s),generate_series('2026-10-10'::date,'2026-10-11'::date,interval '1 day') days(d);`);
      expect((await read()).hotspots[1].count).toBe(0);
      expect((await read('2026-10-10T08:00:00Z')).hotspots[1].count).toBeNull();
      await db.exec('set role anon;');
      await expect(db.query('select * from cme_observation_heads')).rejects.toThrow();
      await expect(db.query("select cme_archive_analytics(now()-interval '7 days',now(),null,null)")).rejects.toThrow();
    }finally{await db.close();}
  },30000);
  it('deduplicates requests, fences stale workers, retains failures and resumes only failed tasks',async()=>{
    const db=await fixture();
    try{
      const job={id:'00000000-0000-0000-0000-000000000001',request_key:'fixture',start_at:'2026-10-01T00:00:00Z',end_at:'2026-10-02T00:00:00Z'};
      const tasks=[{task_key:'planner',kind:'firms_plan',payload:{}}];
      const enqueue=()=>db.query('select cme_archive_enqueue($1,$2)',[JSON.stringify(job),JSON.stringify(tasks)]);
      await enqueue();await enqueue();
      const token='00000000-0000-0000-0000-000000000010';
      const claim=async()=>(await db.query<{v:any}>('select cme_archive_claim($1) v',[token])).rows[0].v;
      const t=await claim();expect(t.attempts).toBe(1);expect(await claim()).toBeNull();
      await expect(db.query('select cme_archive_finish($1,$2,$3,$4,$5)',[t.id,job.id,'{"status":"received"}','[]','[]'])).rejects.toThrow('worker lease lost');
      await db.query('select cme_archive_finish($1,$2,$3,$4,$5)',[t.id,token,'{"status":"unavailable","error":"timeout"}','[]','[]']);
      await db.exec("update cme_archive_tasks set available_at=now()-interval '1 minute'");
      expect((await claim()).attempts).toBe(2);
      await db.exec("update cme_archive_tasks set attempts=3,lease_until=now()-interval '1 second'");
      expect(await claim()).toBeNull();
      const state=(await db.query<{v:any}>('select cme_archive_job_status(null) v')).rows[0].v[0];
      expect(state.status).toBe('failed');expect(state.detail[0].attempt_log.length).toBeGreaterThan(2);
      await db.query('select cme_archive_retry($1)',[job.id]);expect((await claim()).attempts).toBe(1);
      await db.query('select cme_archive_finish($1,$2,$3,$4,$5)',[t.id,token,'{"status":"received"}','[]','[]']);
      expect((await db.query<{v:any}>('select cme_archive_job_status(null) v')).rows[0].v[0].status).toBe('completed');
      // Reprocessing a completed task for a corrected scope starts another run,
      // even when its retry attempt counter is reset.
      await db.exec("update cme_archive_tasks set status='queued',attempts=0,available_at=now()");
      const nextToken='00000000-0000-0000-0000-000000000011';
      await db.query('select cme_archive_claim($1)',[nextToken]);
      await db.query('select cme_archive_finish($1,$2,$3,$4,$5)',[t.id,nextToken,'{"status":"received"}','[]','[]']);
      expect((await db.query<{n:number}>('select count(*)::int n from cme_archive_runs')).rows[0].n).toBe(2);
      await db.exec('set role authenticated;');
      await expect(db.query('select * from cme_archive_tasks')).rejects.toThrow();
      await expect(db.query('select cme_archive_job_status(null)')).rejects.toThrow();
    }finally{await db.close();}
  },30000);
});
