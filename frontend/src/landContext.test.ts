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
  ['A902','ปลา','water'],['U201','หมู่บ้าน','built'],['','ป่าเต็งรัง','dipterocarp'],['','ป่าเบญจพรรณ','mixed_deciduous'],['OTHER','ป่าเต็งรัง','dipterocarp']
])('client fallback respects the same explicit land-use meanings (%s)',(code,name,kind)=>{
  const {dom,c}=setup();expect(c.direct(code,name).kind).toBe(kind);dom.window.close();
});
it('does not infer subtype from jurisdiction codes or ambiguous mixed map-unit codes',()=>{
  const {dom,c}=setup();expect(c.direct('NRF','ป่าสงวน')).toBeNull();expect(c.direct('A101+F201','พื้นที่ผสม')).toBeNull();dom.window.close();
});
it('shows rice immediately without exposing the code and keeps cited details when the API fails',async()=>{
  const {dom,w,c,host}=setup({fail:true});const h={lat:18.8,lon:98.9,landuse_type:'A101',landuse_name:'นาข้าว'};
  host.innerHTML=c.summary(h)+c.details(h);await tick();await c.hydrate(host);
  const first=host.querySelector('.land-context-summary').textContent;
  expect(first).toContain('คาดว่าเป็นการเผาในไร่');expect(first).toContain('พื้นที่เกษตร (นาข้าว)');expect(first).toContain('ไม่ใช่ไฟป่า');
  expect(host.querySelector('.land-kind').textContent).toContain('พื้นที่เกษตร (นาข้าว) · คาดว่าเป็นการเผาในแปลง ไม่ใช่ไฟป่า');
  expect(host.textContent).not.toContain('A101');
  const facts=host.querySelectorAll('.land-context-fact:not(.land-kind):not(.seasonal-fuel):not(.spread-hint)');
  expect(facts).toHaveLength(4);
  facts.forEach((row:any)=>{
    expect(row.textContent).toContain('ประเมินจากแผนที่ ไม่ใช่การสำรวจในพื้นที่');expect(row.querySelector('a[href^="https://"]')).not.toBeNull();
  });
  expect(host.textContent).toContain('ปริมาณเชื้อเพลิงที่เคยวัด (ข้อมูลอ้างอิง)');
  expect(host.textContent).toContain('ไม่ใช่ค่าที่วัด ณ จุดนี้');
  expect(host.textContent).not.toContain('ต่ำ/กลาง/สูง');
  expect(w.fetch.mock.calls.filter(([url]:any)=>url.startsWith('/api/land-context?'))).toHaveLength(1);
  expect(w.fetch.mock.calls.every(([,options]:any)=>!options?.headers?.Authorization)).toBe(true);dom.window.close();
});
it('uses a generic forest profile and cited historical provincial context without assigning a point subtype',async()=>{
  const result={kind:'unknown_forest',headline:'พื้นที่ป่า/ต้นไม้ (จุดนี้ยังระบุชนิดป่าไม่ได้)',sources:[{name:'ESA WorldCover',year:2021,url:'https://esa-worldcover.org/en/data-access'}],reference:reference.profiles.unknown_forest,reference_sources:reference.sources,province_context:reference.province_context};
  const {dom,c,host}=setup({result});const h={lat:18.8,lon:98.9};host.innerHTML=c.summary(h)+c.details(h);await c.hydrate(host);
  const text=host.querySelector('.land-kind').textContent;
  expect(text).toContain('ปี 2021');expect(text).toContain(reference.province_context.context_text);
  expect(text).toContain('สถิติระดับจังหวัดในอดีต');expect(text).not.toContain('ป่าไม่ผลัดใบ');
  expect(text).toContain(reference.profiles.unknown_forest.fuel_level.brief);expect(text).toContain('ค่าจากพื้นที่ศึกษา ไม่ใช่ ณ จุดนี้');
  expect(host.querySelector('a[href$="#page=2"]')).not.toBeNull();dom.window.close();
});
it('rejects a stale CGLS response from an older backend during a staged release',async()=>{
  const result={kind:'evergreen',headline:'ป่าไม่ผลัดใบ',sources:[{name:'Copernicus CGLS-LC100',year:2019,url:'https://zenodo.org/records/3939050'}],reference:reference.profiles.evergreen};
  const {dom,c,host}=setup({result});host.innerHTML=c.summary({lat:17.8,lon:98.4})+c.details({lat:17.8,lon:98.4});await c.hydrate(host);
  expect(host.textContent).not.toContain('ป่าไม่ผลัดใบ');expect(host.textContent).not.toContain('CGLS');dom.window.close();
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

it('first screen shows a seasonal dryness level only where a source covers the kind, with its Bangkok month',()=>{
  const {dom,c}=setup();
  const at=(iso:string)=>new Date(iso);
  expect(c.seasonalFuel('dipterocarp',at('2026-03-10T03:00:00Z'))).toMatchObject({level:3,label:'มาก'});
  expect(c.seasonalFuel('mixed_deciduous',at('2026-07-10T03:00:00Z'))).toMatchObject({level:1,label:'น้อย'});
  expect(c.seasonalFuel('deciduous',at('2026-11-10T03:00:00Z'))).toMatchObject({level:2,label:'เริ่มแห้ง'});
  // 30 April 20:00 UTC is already 1 May in Bangkok: the rainy-season row.
  expect(c.seasonalFuel('deciduous',at('2026-04-30T20:00:00Z')).label).toBe('น้อย');
  expect(c.seasonalFuel('unknown_forest',at('2026-02-01T03:00:00Z')).condition).toBe('ถ้าเป็นป่าผลัดใบ');
  expect(c.seasonalFuel('crop',at('2026-02-01T03:00:00Z')).label).toBe('มาก');
  expect(c.seasonalFuel('crop',at('2026-08-01T03:00:00Z'))).toBeNull();
  for(const kind of ['evergreen','plantation','built','water','bare','unknown'])expect(c.seasonalFuel(kind,at('2026-03-01T03:00:00Z'))).toBeNull();
  for(const kind of ['dipterocarp','crop','grass'])for(const r of c.seasonalFuel(kind,at('2026-03-01T03:00:00Z')).refs){
    expect(reference.sources[r.id].url).toMatch(/^https:\/\//);
  }
  dom.window.close();
});
it('the first screen never calls a hotspot a confirmed forest fire and drops the bar where no source covers the kind',async()=>{
  const result={kind:'evergreen',headline:'ป่าไม่ผลัดใบ',label:'ป่าไม่ผลัดใบ',sources:[{name:'ESA WorldCover',year:2021,url:'https://esa-worldcover.org/en/data-access'}],reference:reference.profiles.evergreen,reference_sources:reference.sources};
  const {dom,c,host}=setup({result});host.innerHTML=c.summary({lat:18.8,lon:98.9})+c.details({lat:18.8,lon:98.9});await c.hydrate(host);
  const first=host.querySelector('.land-context-summary');
  expect(first.textContent).toContain('จุดความร้อนในป่า');expect(first.textContent).not.toContain('น่าจะเป็นไฟป่า');expect(first.textContent).not.toContain('คาดว่าเป็นไฟป่า');
  expect(first.querySelector('.hs-level')).toBeNull();expect(first.textContent).not.toContain('เชื้อเพลิงแห้ง');
  expect(host.querySelector('.land-context-reference').textContent).toContain(reference.profiles.evergreen.fuel_level.text);
  dom.window.close();
});
it('a report popup is labelled as an unconfirmed user report, and an old point is drawn without the live pulse',()=>{
  const {dom,c,host}=setup();
  host.innerHTML=c.summary({latitude:18.8,longitude:98.9,reported_at:'2020-01-01T00:00:00Z'},{report:true});
  expect(host.textContent).toContain('รายงานไฟจากผู้ใช้ (ยังไม่ยืนยัน)');
  expect(host.querySelector('.hs-dot').classList.contains('old')).toBe(true);dom.window.close();
});
