import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const source=readFileSync(resolve(__dirname,'../public/public-guidance.js'),'utf8');
const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
function load(){const dom=new JSDOM('',{runScripts:'outside-only'});dom.window.eval(source);return {dom,G:(dom.window as any).CmePublicGuidance};}

it.each([
  [0,'ดีมาก'],[15,'ดีมาก'],[15.1,'ดี'],[25,'ดี'],[25.1,'ปานกลาง'],[37.5,'ปานกลาง'],
  [37.6,'เริ่มมีผลต่อสุขภาพ'],[75,'เริ่มมีผลต่อสุขภาพ'],[75.1,'มีผลต่อสุขภาพ'],[300,'มีผลต่อสุขภาพ'],
])('PM2.5 %s µg/m³ maps to the PCD AQI B.E. 2566 level %s',(v,label)=>{
  const {dom,G}=load();const l=G.pmLevel(v);expect(l.label).toBe(label);expect(l.advice.length).toBeGreaterThan(5);
  expect(l.url).toBe('https://www.pcd.go.th/pcd_news/30028/');expect(l.source).toContain('ค่าเฉลี่ย 24 ชม.');dom.window.close();
});
it('missing or invalid PM2.5 gives no level instead of a guess',()=>{
  const {dom,G}=load();for(const v of [null,undefined,'',NaN,-1])expect(G.pmLevel(v)).toBeNull();dom.window.close();
});
it('near me prefers detections within 24 hours and counts the 5 km radius',()=>{
  const {dom,G}=load();const now=Date.parse('2026-03-10T10:00:00Z');
  const iso=(h:number)=>new Date(now-h*3600e3).toISOString();
  const me={lat:18.80,lon:98.95};
  const hs=[{lat:18.801,lon:98.951,detected_at:iso(72)},{lat:18.83,lon:98.95,detected_at:iso(3)},{lat:18.90,lon:98.95,detected_at:iso(5)}];
  const r=G.nearMe(me,hs,{now});
  expect(r.nearestAny.ageHours).toBeCloseTo(72);
  expect(r.nearestFresh.ageHours).toBeCloseTo(3);expect(r.nearestFresh.km).toBeCloseTo(3.34,1);
  expect(Math.round(r.nearestFresh.deg)).toBe(0);
  expect(r.freshWithin).toBe(1);
  expect(G.nearMe(me,[],{now}).nearestAny).toBeNull();dom.window.close();
});
it('the first screen always offers the 1362 hotline and old PM labels use the same thresholds',()=>{
  expect(html).toMatch(/<a class="map-fab call-fab" id="callFireHotlineBtn" href="tel:1362"/);
  expect(html).toContain("function pmAqiLabel(p){ return CmePublicGuidance.pmLevel(p)?.label||'—'; }");
  expect(html).not.toContain("p>90?'อันตราย'");
  expect(html.indexOf('/public-guidance.js')).toBeLessThan(html.indexOf('/land-context.js'));
});
