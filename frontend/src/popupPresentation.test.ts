import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
function setup(){
  const dom=new JSDOM('<main id="host"></main>',{runScripts:'outside-only'}),w=dom.window as any;
  for(const file of ['decision-support.js','forest-coordination.js'])w.eval(readFileSync(resolve(__dirname,'../public',file),'utf8'));
  w.CmeCoordination.init({agencies:()=>[],forests:()=>[],tambons:()=>[],districts:()=>[]});
  w.Date.now=()=>Date.parse('2026-10-18T06:05:00Z');
  w.fmtFrp=()=>'';w.gMapsLink=()=>'';
  for(const name of ['hotspotPopupHtml','manualReportPopupHtml'])w.eval(html.match(new RegExp('function '+name+'\\([^]*?\\n\\}'))![0]);
  return {dom,w,host:w.document.getElementById('host')};
}
it('satellite popup leads with age and Bangkok detection time before the card, with a single 1362 link',()=>{
  const {dom,w,host}=setup();
  host.innerHTML=w.hotspotPopupHtml({id:'fixture',lat:18.8,lon:98.9,detected_at:'2026-10-15T06:05:00Z',sat:'VIIRS',district:'Fixture'});
  const first=host.firstElementChild;
  expect(first.className).toBe('hotspot-detected-time');
  expect(first.textContent).toMatch(/ตรวจพบ 3 วันที่แล้ว \(15 ต\.ค\.\s*13:05\) · ดาวเทียม/);
  expect(first.nextElementSibling.className).toBe('coordination-card');
  expect(host.querySelectorAll('a[href="tel:1362"]')).toHaveLength(1);dom.window.close();
});
it('manual-report popup also leads with the observation age and retains exactly one emergency link',()=>{
  const {dom,w,host}=setup();
  host.innerHTML=w.manualReportPopupHtml({latitude:18.8,longitude:98.9,reported_at:'2026-10-15T06:05:00Z',reporter_name:'Fixture'});
  expect(host.firstElementChild.textContent).toContain('ตรวจพบ 3 วันที่แล้ว');
  expect(host.firstElementChild.textContent).toContain('รายงานโดยผู้ใช้');
  expect(host.querySelectorAll('a[href="tel:1362"]')).toHaveLength(1);dom.window.close();
});
it('missing or future timestamps are not disguised as recent detections',()=>{
  const {dom,w}=setup();
  expect(w.CmeEvidence.observationTimeHtml(null)).toContain('ยังไม่ทราบเวลาตรวจพบ');
  expect(w.CmeEvidence.observationTimeHtml('2099-01-01T00:00:00Z')).toContain('เวลาตรวจพบอยู่ในอนาคต');dom.window.close();
});
