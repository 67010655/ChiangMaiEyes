import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
function setup(){
  const dom=new JSDOM('<main id="host"></main>',{runScripts:'outside-only'}),w=dom.window as any;
  for(const file of ['decision-support.js','forest-coordination.js','land-context.js'])w.eval(readFileSync(resolve(__dirname,'../public',file),'utf8'));
  w.CmeCoordination.init({agencies:()=>[],forests:()=>[],tambons:()=>[],districts:()=>[]});
  w.Date.now=()=>Date.parse('2026-10-18T06:05:00Z');
  w.fmtFrp=()=>'';w.gMapsLink=()=>'';
  for(const name of ['popupWhereHtml','popupActionsHtml','hotspotPopupHtml','manualReportPopupHtml'])w.eval(html.match(new RegExp('function '+name+'\\([^]*?\\n\\}'))![0]);
  return {dom,w,host:w.document.getElementById('host')};
}
it('satellite popup leads with age and Bangkok detection time before the card, with a single 1362 link',()=>{
  const {dom,w,host}=setup();
  host.innerHTML=w.hotspotPopupHtml({id:'fixture',lat:18.8,lon:98.9,detected_at:'2026-10-15T06:05:00Z',sat:'VIIRS',district:'Fixture'});
  const first=host.querySelector('.hs-pop').firstElementChild;
  expect(first.className).toBe('hotspot-detected-time');
  expect(first.textContent).toMatch(/ตรวจพบ 3 วันที่แล้ว \(15 ต\.ค\.\s*13:05\) · ดาวเทียม/);
  expect(first.nextElementSibling.className).toBe('land-context-summary');
  expect(host.querySelector('.land-context-details summary').textContent).toBe('รายละเอียดและที่มาของข้อมูล');
  // Contacts, caveats and the raw detection stay one tap away.
  expect(host.querySelector('.land-context-details .coordination-card')).not.toBeNull();
  expect(host.querySelector('.land-context-details').textContent).toContain('VIIRS');
  expect(host.querySelectorAll('.hs-actions a[href="tel:1362"]')).toHaveLength(1);
  expect(host.querySelector('.hs-actions a.hs-nav').getAttribute('href')).toContain('destination=18.8,98.9');dom.window.close();
});
it('manual-report popup also leads with the observation age and retains exactly one emergency link',()=>{
  const {dom,w,host}=setup();
  host.innerHTML=w.manualReportPopupHtml({latitude:18.8,longitude:98.9,reported_at:'2026-10-15T06:05:00Z',reporter_name:'Fixture'});
  const first=host.querySelector('.hs-pop').firstElementChild;
  expect(first.textContent).toContain('ตรวจพบ 3 วันที่แล้ว');
  expect(first.textContent).toContain('รายงานโดยผู้ใช้');
  expect(host.textContent).toContain('รายงานไฟจากผู้ใช้ (ยังไม่ยืนยัน)');
  expect(host.querySelectorAll('.hs-actions a[href="tel:1362"]')).toHaveLength(1);dom.window.close();
});
it('distance from the user appears only after they shared their location',()=>{
  const {dom,w,host}=setup();
  const h={id:'fixture',lat:18.8,lon:98.9,detected_at:'2026-10-15T06:05:00Z',sat:'VIIRS',district:'แม่อาย',subdistrict:'แม่นาวาง'};
  host.innerHTML=w.hotspotPopupHtml(h);expect(host.textContent).not.toContain('ห่างคุณ');
  expect(host.querySelector('.hs-where').textContent).toContain('ต.แม่นาวาง อ.แม่อาย');
  w.CmeMyLocation={lat:18.8,lon:98.95};host.innerHTML=w.hotspotPopupHtml(h);
  expect(host.querySelector('.hs-where').textContent).toMatch(/ห่างคุณ 5\.3 กม\./);
  dom.window.close();
});
it('missing or future timestamps are not disguised as recent detections',()=>{
  const {dom,w}=setup();
  expect(w.CmeEvidence.observationTimeHtml(null)).toContain('ยังไม่ทราบเวลาตรวจพบ');
  expect(w.CmeEvidence.observationTimeHtml('2099-01-01T00:00:00Z')).toContain('เวลาตรวจพบอยู่ในอนาคต');dom.window.close();
});
