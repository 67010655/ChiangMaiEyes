import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createContext,runInContext} from 'node:vm';
import {JSDOM} from 'jsdom';
import {describe,it,expect} from 'vitest';

const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
describe('analytics uses the chosen history, including request races and data classes',()=>{
  it('a late seven-day response cannot overwrite a newly selected 180-day range',async()=>{
    const dom=new JSDOM(html),pending:any[]=[],rendered:number[]=[];
    const ctx=createContext({document:dom.window.document,Date,URLSearchParams,
      fetchJson:(url:string)=>new Promise(resolve=>pending.push({url,resolve})),
      renderArchiveAnalytics:(h:any)=>rendered.push(h.days)});
    const start=html.indexOf('let selectedHistory=null'),end=html.indexOf('function renderArchiveAnalytics(',start);
    runInContext(html.slice(start,end),ctx);
    const first=runInContext("renderAnalytics('7d')",ctx),second=runInContext("renderAnalytics('180d')",ctx);
    pending[1].resolve({days:180,status:'available',analytics:{hotspots:[]}});await second;
    pending[0].resolve({days:7,status:'available',analytics:{hotspots:[]}});await first;
    expect(rendered).toEqual([180]);
    expect(pending.map(p=>p.url)).toEqual(['/api/history?days=7','/api/history?days=180']);
    dom.window.close();
  });
  it('keeps measured/model PM separate, falls back to model only when no station data, and counts complete days honestly',()=>{
    const dom=new JSDOM(html),renders:any[]=[];
    const ctx=createContext({document:dom.window.document,allForests:[],hotspots:[],firePredictions:null,districtLayerRef:{},
      normalizeDistrictName:(x:any)=>x,window:{},
      CmeAnalyticsSummary:{render:(_el:any,h:any,o:any)=>renders.push({h,o})}});
    const start=html.indexOf('function renderArchiveAnalytics('),end=html.indexOf('// Card actions:',start);
    runInContext(html.slice(start,end),ctx);
    ctx.h={days:7,start:'2026-10-01T00:00:00Z',end:'2026-10-08T00:00:00Z',notes:[],analytics:{
      total:4,hotspots:[{date:'2026-10-02',count:2,source_requests_complete:true,partial_day:false},
                      {date:'2026-10-03',count:2,source_requests_complete:false,partial_day:false}],
      pm25:[{date:'2026-10-02',value:8,samples:2,measurement_kind:'measured'},
            {date:'2026-10-02',value:80,samples:2,measurement_kind:'model'}]}};
    runInContext('renderArchiveAnalytics(h)',ctx);
    // The data-range line says only 1 of 2 full days had complete satellite requests.
    expect(dom.window.document.getElementById('anStatus')!.textContent).toContain('ครบ 1/2 วันเต็ม');
    expect(renders[0].h).toBe(ctx.h);
    dom.window.close();
    // The cards pick PM by kind: station first, model only when there is no station value.
    const w=new JSDOM('',{runScripts:'outside-only'}).window as any;
    w.eval(readFileSync(resolve(__dirname,'../public/analytics-summary.js'),'utf8'));
    expect(w.CmeAnalyticsSummary.pmSeries(ctx.h.analytics).pms.map((p:any)=>p.value)).toEqual([8]);
    const noStation={pm25:[{date:'2026-10-02',value:80,samples:2,measurement_kind:'model'}]};
    const m=w.CmeAnalyticsSummary.pmSeries(noStation);
    expect(m.kind).toBe('model');expect(m.pms.map((p:any)=>p.value)).toEqual([80]);
    w.close();
  });
});
