import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {runInNewContext} from 'node:vm';
import {describe,it,expect} from 'vitest';

const context: any = {};
runInNewContext(readFileSync(resolve(__dirname,'../public/decision-support.js'),'utf8'),context);
const e = context.CmeEvidence;
const now = Date.parse('2026-10-09T12:00:00Z');
const geometry = {type:'Polygon',coordinates:[[[98,18],[99,18],[99,19],[98,19],[98,18]],[[98.4,18.4],[98.6,18.4],[98.6,18.6],[98.4,18.6],[98.4,18.4]]]};
const items = [
  {id:'inside',lat:18.2,lon:98.2,detected_at:'2026-10-09T10:00:00Z'},
  {id:'hole',lat:18.5,lon:98.5,detected_at:'2026-10-09T10:00:00Z'},
  {id:'old',lat:18.2,lon:98.2,detected_at:'2026-10-07T10:00:00Z'},
  {id:'future',lat:18.2,lon:98.2,detected_at:'2026-10-10T10:00:00Z'},
  {id:'invalid',lat:18.2,lon:98.2,detected_at:'unknown'},
];
describe('evidence selection for public summaries and export',()=>{
  it('uses the native confidence category, never treating a legacy rank as a probability',()=>{
    expect(e.confidenceLevel({confidence:75,confidence_level:'nominal'})).toBe('nominal');
    expect(e.confidenceLevel({confidence:90})).toBe('unknown');
    expect(e.confidenceLabel('nominal')).toContain('nominal');
    const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
    const norm=html.match(/function normHotspots\(items\)\{[\s\S]*?\n\}/)![0];
    const runtime:any={CmeEvidence:e,bangkokHourFromIso:()=>13,minutesAgo:()=>0};
    runInNewContext(norm+'\nresult=normHotspots([{id:"fixture",confidence:75,confidence_level:"nominal"}]);',runtime);
    expect(runtime.result[0].conf).toBe('nominal');
  });
  it('renders real observation rows and distinguishes old markers without crashing',()=>{
    const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
    const render=html.match(/function renderHotspots\(\)\{[\s\S]*?\n\}/)![0];
    const markers: any[]=[];
    class Clock extends Date {static now(){return now;}}
    const runtime: any={
      innerHeight:812,
      Date:Clock, hotspots:[{lat:18,lon:99,conf:'high',frp:3,detected_at:'2026-10-09T10:00:00Z'},{lat:18,lon:99,conf:'high',frp:3,detected_at:'2026-10-07T10:00:00Z'}],
      frpColor:()=> '#ff8a3d',clearForestProximity:()=>{},
      document:{getElementById:()=>({textContent:''})},
      layers:{hotspots:{clearLayers:()=>{},addLayer:(m:any)=>markers.push(m)}},
      L:{divIcon:(o:any)=>o,marker:()=>({opacity:null as number|null,setOpacity(v:number){this.opacity=v;return this;},bindPopup(){return this;},on(){return this;}})}
    };
    runtime.window=runtime;
    runInNewContext(readFileSync(resolve(__dirname,'../public/decision-support.js'),'utf8')+'\n'+render+'\nrenderHotspots();',runtime);
    expect(markers).toHaveLength(2);
    expect(markers.map(m=>m.opacity)).toEqual([1,.38]);
  });
  it('keeps missing history distinct from observed zero counts',()=>{
    expect(e.dailyStats([]).total).toBeNull();
    expect(e.dailyStats([]).max).toBeNull();
    expect(e.dailyStats([0,0]).total).toBe(0);
    expect(e.dailyStats([0,0]).sd).toBe(0);
  });
  it('summarizes only known daily samples without turning gaps into zero',()=>{
    expect(e.dailyStats([2,null,4,undefined]).n).toBe(2);
    expect(e.dailyStats([2,null,4,undefined]).mean).toBe(3);
    expect(e.dailyStats([2,4]).median).toBe(3);
  });
  it('excludes observations outside the window, future dates, and unknown times',()=>{
    expect(e.filterHotspots(items,{now}).map((x:any)=>x.id)).toEqual(['inside','hole']);
  });
  it('uses the actual forest polygon and excludes holes rather than centroid radius',()=>{
    expect(e.filterHotspots(items,{now,forest:{boundary:geometry}}).map((x:any)=>x.id)).toEqual(['inside']);
  });
  it('supports MultiPolygon forests',()=>{
    expect(e.inBoundary(18.2,98.2,{type:'MultiPolygon',coordinates:[geometry.coordinates]})).toBe(true);
    expect(e.inBoundary(18.5,98.5,{type:'MultiPolygon',coordinates:[geometry.coordinates]})).toBe(false);
  });
  it('selects a point radius without exporting unrelated provincial observations',()=>{
    expect(e.filterHotspots(items,{now,point:{lat:18.2,lon:98.2},radiusKm:1}).map((x:any)=>x.id)).toEqual(['inside']);
  });
  it('converts meteorological FROM bearing to TO without reversing east and north',()=>{
    expect(e.windTo(0)).toBe(180);
    expect(e.windTo(270)).toBe(90);
    expect(e.windTo(-90)).toBe(90);
  });
  it('escapes untrusted forest/station names before using report markup',()=>{
    expect(e.escapeHtml('<img src="x" onerror=alert(1)>')).toBe('&lt;img src=&quot;x&quot; onerror=alert(1)&gt;');
  });
});
