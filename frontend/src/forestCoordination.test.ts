import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it, vi } from 'vitest';

const evidence=readFileSync(resolve(__dirname,'../public/decision-support.js'),'utf8');
const coordination=readFileSync(resolve(__dirname,'../public/forest-coordination.js'),'utf8');
const rectangle=(w:number,s:number,e:number,n:number)=>({type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]});
const mine={forest_id:'doi-pui',name:'ดอยปุย',amphoe:'เมืองเชียงใหม่',latitude:18.8,longitude:98.895,boundary:rectangle(98.89,18.79,98.9,18.81)};
const neighbor={forest_id:'ban-pong',name:'บ้านปง',amphoe:'หางดง',latitude:18.8,longitude:98.94,boundary:rectangle(98.93,18.79,98.95,18.81)};
const third={forest_id:'other',name:'อีกป่า',amphoe:'สะเมิง',latitude:18.8,longitude:98.97,boundary:rectangle(98.96,18.79,98.98,18.81)};
const admin=[{geometry:rectangle(98.9,18.7,99,18.9),properties:{tambon_th:'บ้านปง',amphoe_th:'หางดง'}}];
const tick=()=>new Promise(r=>setTimeout(r,5));
function setup(){
  const dom=new JSDOM('<main id="host"></main>',{url:'http://localhost/',runScripts:'outside-only'}),w=dom.window as any;
  let user:any=null;
  w.eval(evidence);w.eval(coordination);
  w.fetch=vi.fn(async()=>({ok:true,json:async()=>[{forest_id:'doi-pui',has_representative:false},{forest_id:'ban-pong',has_representative:true}]}));
  w.CmeCoordination.init({forests:()=>[neighbor,third,mine],tambons:()=>admin,districts:()=>[],user:()=>user,session:async()=>user?{user,access_token:'fixture-token'}:null});
  return {dom,w,c:w.CmeCoordination,host:w.document.getElementById('host'),setUser:(v:any)=>{user=v;}};
}
it('finds forests across district lines by edge distance and leads with boundary-derived location',()=>{
  const {dom,c}=setup(),rows=c.nearest(18.8,98.901);
  expect(rows.map((r:any)=>r.forest.forest_id)).toEqual(['doi-pui','ban-pong','other']);
  expect(rows[0].km).toBeCloseTo(.105,2);
  expect(c.administrativeArea(18.8,98.901)).toEqual({status:'matched',tambon:'บ้านปง',district:'หางดง'});
  const html=c.html(18.8,98.901,{myForestId:'doi-pui'});
  expect(html).toContain('จุดนี้อยู่ ต.บ้านปง อ.หางดง · ป่าชุมชนที่ใกล้ที่สุด: ดอยปุย');
  expect(html).toContain('อยู่นอกเขตอำเภอ แต่ป่าเราใกล้ที่สุด');
  expect(html).toContain('ป่าข้างเคียง: บ้านปง, อีกป่า');
  expect(html).toContain('ระยะเส้นตรง ไม่ใช่ระยะเดินทาง');
  dom.window.close();
});
it('handles polygon holes, multipolygons and shared edges without substituting a source district',()=>{
  const {dom,c}=setup();
  const g=rectangle(98.8,18.7,99,19);g.coordinates.push(rectangle(98.85,18.8,98.95,18.9).coordinates[0]);
  expect(c.boundaryDistance({lat:18.85,lon:98.9},g)).toBeGreaterThan(5);
  expect(c.boundaryDistance({lat:18.75,lon:98.9},g)).toBe(0);
  expect(c.covers({lat:18.8,lon:98.9},{type:'MultiPolygon',coordinates:[mine.boundary.coordinates]})).toBe(true);
  expect(c.administrativeArea(0,0).status).toBe('unmatched');
  expect(c.html(null,null)).toContain('ยังไม่มีพิกัด');
  expect(c.nearest('',null)).toEqual([]);
  dom.window.close();
});
it('marks ambiguous administrative boundaries and uses a labelled reference for a damaged forest polygon',()=>{
  const {dom,c}=setup();
  c.init({forests:()=>[{...mine,boundary_quality:'needs_review'}],tambons:()=>[...admin,...admin]});
  expect(c.administrativeArea(18.8,98.901).status).toBe('ambiguous');
  expect(c.html(18.8,98.901)).toContain('(จุดอ้างอิงป่า)');
  expect(c.html(18.8,98.901)).not.toContain('จุดนี้อยู่ ต.บ้านปง');
  dom.window.close();
});
it('public card does not fetch or render private contact data, even if extras enter the status response',async()=>{
  const {dom,w,c,host}=setup();
  w.fetch.mockImplementation(async()=>({ok:true,json:async()=>[{forest_id:'doi-pui',has_representative:false,representatives:[{name:'PRIVATE',email:'secret@example.test'}]},{forest_id:'ban-pong',has_representative:true}]}));
  host.innerHTML=c.html(18.8,98.901);await c.hydrate(host);
  expect(host.textContent).toContain('ยังไม่มีผู้ประสานงานของป่านี้');
  expect(host.textContent).toContain('เข้าสู่ระบบเพื่อดูชื่อและปุ่มติดต่อ');
  expect(host.innerHTML).not.toContain('PRIVATE');expect(host.innerHTML).not.toContain('secret@example.test');
  expect(host.querySelector('a[href="tel:1362"]')).not.toBeNull();
  expect(w.fetch.mock.calls.every(([url,opts]:any)=>url.includes('/contact-status?')&&!opts.headers.Authorization)).toBe(true);
  dom.window.close();
});
it('confirmed login fetches private contacts, escapes names, and logout removes them immediately',async()=>{
  const {dom,w,c,host,setUser}=setup();setUser({id:'viewer'});
  w.fetch.mockImplementation(async(url:string)=>({ok:true,json:async()=>url.includes('/forest-contacts?')?[{forest_id:'doi-pui',representatives:[{name:'Approved <img src=x onerror=bad()>',email:'approved@example.test'}]}]:[]}));
  host.innerHTML=c.html(18.8,98.901);await c.hydrate(host);
  expect(host.textContent).toContain('Approved <img');expect(host.querySelector('img')).toBeNull();
  expect(host.querySelector('a[href^="mailto:"]').getAttribute('href')).toBe('mailto:approved%40example.test');
  expect(w.fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer fixture-token');
  setUser(null);const done=c.authChanged();
  expect(host.innerHTML).not.toContain('Approved');expect(host.querySelector('a[href^="mailto:"]')).toBeNull();
  await done;dom.window.close();
});
it('discards a private response that arrives after logout and has no persistent contact cache',async()=>{
  const {dom,w,c,host,setUser}=setup();setUser({id:'viewer'});
  let release:any;
  w.fetch.mockImplementation((url:string)=>url.includes('/forest-contacts?')?new Promise(r=>{release=r;}):Promise.resolve({ok:true,json:async()=>[]}));
  host.innerHTML=c.html(18.8,98.901);const pending=c.hydrate(host);await tick();
  setUser(null);await c.authChanged();
  release({ok:true,json:async()=>[{forest_id:'doi-pui',representatives:[{name:'LATE PRIVATE',email:'late@example.test'}]}]});await pending;
  expect(host.textContent).not.toContain('LATE PRIVATE');expect(host.querySelector('a[href^="mailto:"]')).toBeNull();
  expect(w.localStorage.length).toBe(0);dom.window.close();
});
it('backend failure retains public geography and emergency contacts and does not claim there is no representative',async()=>{
  const {dom,w,c,host}=setup();w.fetch.mockRejectedValue(new Error('offline'));
  host.innerHTML=c.html(18.8,98.901);await c.hydrate(host);
  expect(host.textContent).toContain('ต.บ้านปง อ.หางดง');expect(host.textContent).toContain('ยังตรวจสอบผู้ประสานงานไม่ได้');
  expect(host.textContent).not.toContain('ยังไม่มีผู้ประสานงานของป่านี้');expect(host.querySelector('a[href="tel:1362"]')).not.toBeNull();
  dom.window.close();
});
it('recalculates an open popup after asynchronous contact content changes its height',async()=>{
  const {dom,c,host}=setup(),update=vi.fn();
  c.popupOpened({getElement:()=>host,isOpen:()=>true,_updateLayout:update,_updatePosition:vi.fn(),_adjustPan:vi.fn()});
  host.innerHTML=c.html(18.8,98.901);await c.hydrate(host);
  expect(update).toHaveBeenCalled();dom.window.close();
});
it('shows only recent points within five kilometres where this forest is closest across the district line',()=>{
  const {dom,c}=setup(),now=new Date().toISOString();
  const points=[{id:'cross',latitude:18.8,longitude:98.901,detected_at:now},{id:'other-closest',latitude:18.8,longitude:98.94,detected_at:now},{id:'far',latitude:18.8,longitude:99.9,detected_at:now},{id:'old',latitude:18.8,longitude:98.901,detected_at:'2020-01-01T00:00:00Z'}];
  expect(c.nearbyCrossDistrict(points,mine).map((p:any)=>p.id)).toEqual(['cross']);dom.window.close();
});
