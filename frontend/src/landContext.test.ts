import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it, vi } from 'vitest';

const source=readFileSync(resolve(__dirname,'../public/land-context.js'),'utf8');
const evidence=readFileSync(resolve(__dirname,'../public/decision-support.js'),'utf8');
const reference=JSON.parse(readFileSync(resolve(__dirname,'../public/land-context-reference.json'),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,10));
function setup({fail=false,result=null as any}={}){
  const dom=new JSDOM('<main id="host"></main>',{runScripts:'outside-only',url:'http://localhost/'}),w=dom.window as any;
  w.eval(evidence);w.eval(source);
  w.fetch=vi.fn(async(url:string)=>url==='/land-context-reference.json'?{ok:true,json:async()=>reference}:fail?{ok:false,status:503}:{ok:true,json:async()=>result});
  w.CmeLandContext.init();
  return {dom,w,c:w.CmeLandContext,host:w.document.getElementById('host')};
}
it.each([
  ['A101','นาข้าว','crop'],['F201','','deciduous'],['F201','ป่าเบญจพรรณ','mixed_deciduous'],
  ['F202','ป่าเต็งรัง','dipterocarp'],['F202','','unknown_forest'],['F201','ป่าไม่ผลัดใบสมบูรณ์','evergreen'],
  ['F201','ป่าเต็งรัง/ป่าเบญจพรรณ','deciduous'],['F201','ป่าดิบ/ป่าเบญจพรรณ','unknown_forest'],
  ['A902','ปลา','water'],['U201','หมู่บ้าน','built']
])('client fallback respects the same explicit land-use meanings (%s)',(code,name,kind)=>{
  const {dom,c}=setup();expect(c.direct(code,name).kind).toBe(kind);dom.window.close();
});
it('does not infer subtype from jurisdiction codes or ambiguous mixed map-unit codes',()=>{
  const {dom,c}=setup();expect(c.direct('NRF','ป่าสงวน')).toBeNull();expect(c.direct('A101+F201','พื้นที่ผสม')).toBeNull();dom.window.close();
});
it('shows rice immediately without exposing the code and keeps cited details when the API fails',async()=>{
  const {dom,w,c,host}=setup({fail:true});const h={lat:18.8,lon:98.9,landuse_type:'A101',landuse_name:'นาข้าว'};
  host.innerHTML=c.summary(h)+c.details(h);await tick();await c.hydrate(host);
  expect(host.querySelector('.land-context-summary').textContent).toContain('พื้นที่เกษตร (นาข้าว) · น่าจะเป็นการเผาในแปลง ไม่ใช่ไฟป่า');
  expect(host.textContent).not.toContain('A101');
  expect(host.querySelectorAll('.land-context-fact')).toHaveLength(4);
  host.querySelectorAll('.land-context-fact').forEach((row:any)=>{
    expect(row.textContent).toContain('ประเมินจากแผนที่ ไม่ใช่การสำรวจในพื้นที่');expect(row.querySelector('a[href^="https://"]')).not.toBeNull();
  });
  expect(host.textContent).toContain('ยังจัดระดับต่ำ/กลาง/สูงไม่ได้');
  expect(w.fetch.mock.calls.filter(([url]:any)=>url.startsWith('/api/land-context?'))).toHaveLength(1);
  expect(w.fetch.mock.calls.every(([,options]:any)=>!options?.headers?.Authorization)).toBe(true);dom.window.close();
});
it('renders the historical forest class and years returned by the API without calling it mixed deciduous forest',async()=>{
  const result={kind:'mixed_forest',headline:'ป่าผสมหลายชนิด (ยังแยกผลัดใบไม่ได้)',sources:[{name:'Copernicus CGLS-LC100',year:2019,url:'https://zenodo.org/records/3939050'}],reference:reference.profiles.mixed_forest,reference_sources:reference.sources};
  const {dom,c,host}=setup({result});const h={lat:18.8,lon:98.9};host.innerHTML=c.summary(h)+c.details(h);await c.hydrate(host);
  const text=host.querySelector('.land-context-summary').textContent;
  expect(text).toContain('ปี 2019');expect(text).not.toContain('เบญจพรรณ');expect(text).not.toContain('mixed_forest');dom.window.close();
});
it('keeps unknown land context unknown when neither API nor point code can establish a class',async()=>{
  const {dom,c,host}=setup({fail:true});host.innerHTML=c.summary({lat:18.8,lon:98.9});await c.hydrate(host);
  expect(host.textContent).toContain('ยังระบุชนิดพื้นที่ไม่ได้');expect(host.textContent).not.toContain('พื้นที่เกษตร');dom.window.close();
});
it('escapes upstream content instead of allowing executable markup',async()=>{
  const {dom,c,host}=setup({result:{kind:'unknown',headline:'<img src=x onerror=bad()>',sources:[]}});
  host.innerHTML=c.summary({lat:18.8,lon:98.9});await c.hydrate(host);expect(host.querySelector('img')).toBeNull();expect(host.textContent).toContain('<img');dom.window.close();
});
it('ships exactly the backend reference table with source links for every value',()=>{
  expect(readFileSync(resolve(__dirname,'../public/land-context-reference.json'),'utf8')).toBe(readFileSync(resolve(__dirname,'../../backend/app/data/land-context-reference.json'),'utf8'));
  for(const profile of Object.values(reference.profiles) as any[])for(const field of Object.values(profile) as any[]){
    expect(field.refs.length).toBeGreaterThan(0);field.refs.forEach((r:any)=>expect(reference.sources[r.id].url).toMatch(/^https:\/\//));
  }
});
