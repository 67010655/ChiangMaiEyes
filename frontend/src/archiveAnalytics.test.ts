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
  it('keeps measured/model PM separate and excludes incomplete days from correlation and averages',()=>{
    const dom=new JSDOM(html),scatters:any[]=[],stats:any[]=[];
    const ctx=createContext({document:dom.window.document,allForests:[],hotspots:new Array(999),
      CmeEvidence:{escapeHtml:(x:any)=>String(x),stamp:(x:any)=>String(x),dailyStats:(xs:any)=>{stats.push(xs);return {}; }},
      donut:()=>{},histogram:()=>{},trendChart:()=>{},renderEvidenceTimeline:()=>{},
      normalizeSatelliteProduct:(x:any)=>({label:x}),bangkokDayLabel:(x:any)=>x,
      scatterReg:(_id:any,pts:any)=>{scatters.push(pts);return NaN;}});
    const start=html.indexOf('function renderArchiveAnalytics('),end=html.indexOf("document.getElementById('anPmKind').onchange",start);
    runInContext(html.slice(start,end),ctx);
    ctx.h={days:7,start:'2026-10-01T00:00:00Z',end:'2026-10-08T00:00:00Z',notes:[],analytics:{
      total:4,hotspots:[{date:'2026-10-02',count:2,source_requests_complete:true,partial_day:false},
                      {date:'2026-10-03',count:2,source_requests_complete:false,partial_day:false}],
      pm25:[{date:'2026-10-02',value:8,samples:2,measurement_kind:'measured'},
            {date:'2026-10-02',value:80,samples:2,measurement_kind:'model'}],
      frp:{max:6,mean:3,known:2,bins:[2,0,0,0,0,0,0]},hour_histogram:new Array(24).fill(0)}};
    runInContext('renderArchiveAnalytics(h)',ctx);
    expect(dom.window.document.getElementById('anCards')!.textContent).toContain('8.0');
    expect(dom.window.document.getElementById('anCards')!.textContent).not.toContain('999');
    expect(scatters[0]).toEqual([{x:2,y:8}]);expect(stats[0]).toEqual([2]);
    (dom.window.document.getElementById('anPmKind') as HTMLSelectElement).value='model';
    runInContext('renderArchiveAnalytics(h)',ctx);
    expect(dom.window.document.getElementById('anCards')!.textContent).toContain('80.0');
    expect(scatters[1]).toEqual([{x:2,y:80}]);
    dom.window.close();
  });
});
