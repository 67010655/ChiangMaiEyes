import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source=readFileSync(resolve(__dirname,'../public/spread-hint.js'),'utf8');
const reference=JSON.parse(readFileSync(resolve(__dirname,'../public/land-context-reference.json'),'utf8'));
function load(){const dom=new JSDOM('',{runScripts:'outside-only'});dom.window.eval(source);return {dom,H:(dom.window as any).CmeSpreadHint};}
// 10:00 and 22:00 Asia/Bangkok
const DAY=new Date('2026-03-10T03:00:00Z'), NIGHT=new Date('2026-03-10T15:00:00Z');
const wind=(fromDeg:number,kmh:number)=>({ready:true,toDeg:(fromDeg+180)%360,kmh,label:'ลมสถานี'});
const forest=reference.spread_rates.unknown_forest;

describe('spread hint', ()=>{
  it('a wind from the north spreads the fire south, matching the top card convention',()=>{
    const {dom,H}=load();const r=H.build({wind:wind(0,12),terrain:null,rate:null,ageHours:2,now:DAY});
    expect(r.windTo).toBe(180);expect(r.line).toContain('ตามลมไปทางใต้');dom.window.close();
  });
  it('light wind gives no precise downwind direction',()=>{
    const {dom,H}=load();const r=H.build({wind:wind(90,1),terrain:null,rate:null,ageHours:2,now:DAY});
    expect(r.windTo).toBeNull();expect(r.line).toContain('ลมเบา');expect(r.line).not.toContain('ตามลมไปทาง');dom.window.close();
  });
  it('shows upslope only in daytime and only on real slopes, never blended with wind',()=>{
    const {dom,H}=load();const slope={slope_deg:12.5,upslope_to_deg:304};
    const day=H.build({wind:wind(90,10),terrain:slope,rate:null,ageHours:2,now:DAY});
    expect(day.line).toContain('ขึ้นเขาไปทางตะวันตกเฉียงเหนือ');expect(day.line).toContain('ตามลมไปทางตะวันตก');
    const night=H.build({wind:wind(90,10),terrain:slope,rate:null,ageHours:2,now:NIGHT});
    expect(night.line).not.toContain('ขึ้นเขา');expect(night.details.join(' ')).toContain('กลางคืนลมหุบเขามักพัดลง');
    const flat=H.build({wind:wind(90,10),terrain:{slope_deg:1.2,upslope_to_deg:30},rate:null,ageHours:2,now:DAY});
    expect(flat.line).not.toContain('ขึ้นเขา');expect(flat.details.join(' ')).toContain('ค่อนข้างราบ');
    dom.window.close();
  });
  it('says when wind and upslope point the same way',()=>{
    const {dom,H}=load();const r=H.build({wind:wind(120,10),terrain:{slope_deg:15,upslope_to_deg:290},rate:null,ageHours:2,now:DAY});
    expect(r.details.join(' ')).toContain('ไปทางเดียวกัน');dom.window.close();
  });
  it('gives a one-hour rate range only for fresh detections, from the cited reference',()=>{
    const {dom,H}=load();
    const fresh=H.build({wind:wind(0,10),terrain:null,rate:forest,ageHours:3,now:DAY});
    expect(fresh.line).toContain(`${forest.min_m_per_hour}–${forest.max_m_per_hour} ม. ใน 1 ชม.`);
    expect(fresh.line).toContain('ถ้ายังไหม้อยู่');
    const old=H.build({wind:wind(0,10),terrain:null,rate:forest,ageHours:60,now:DAY});
    expect(old.line).not.toContain('ม. ใน 1 ชม.');expect(old.details.join(' ')).toContain('ใช้ทิศนี้เพื่อเฝ้าระวังเท่านั้น');
    dom.window.close();
  });
  it('built-up, water and evergreen areas get no rate',()=>{
    for(const kind of ['built','water','evergreen','plantation','grass','shrub'])expect(reference.spread_rates[kind]).toBeUndefined();
    const {dom,H}=load();const r=H.build({wind:wind(0,10),terrain:null,rate:null,ageHours:1,now:DAY});
    expect(r.line).not.toContain('ม. ใน 1 ชม.');dom.window.close();
  });
  it('rates are copied from the cited pages and the hour range is derived, not typed',()=>{
    expect(reference.spread_rates.dipterocarp).toMatchObject({min_m_min:'0.5',max_m_min:'9',min_m_per_hour:'30',max_m_per_hour:'540'});
    expect(reference.spread_rates.mixed_deciduous).toMatchObject({min_m_min:'0.7',max_m_min:'5',max_m_per_hour:'300'});
    for(const r of Object.values<any>(reference.spread_rates))expect(r.refs.length).toBeGreaterThan(0);
    const {dom,H}=load();expect(H.coneKm(forest)).toBeCloseTo(0.54);dom.window.close();
  });
});

it('an experimental corn rate never reaches the first-screen line',()=>{
  const {dom,H}=load();const crop=reference.spread_rates.crop;expect(crop.in_summary).toBe(false);
  const r=H.build({wind:wind(0,10),terrain:null,rate:crop,ageHours:2,now:DAY});
  expect(r.line).not.toContain('ม. ใน 1 ชม.');expect(r.details.join(' ')).toContain('การทดลองเผาไร่ข้าวโพด');dom.window.close();
});

it('unknown forest keeps the deciduous condition on the first-screen line',()=>{
  const {dom,H}=load();const r=H.build({wind:wind(0,10),terrain:null,rate:forest,ageHours:2,kind:'unknown_forest',now:DAY});
  expect(r.line).toContain('ถ้าเป็นป่าผลัดใบและยังไหม้อยู่');dom.window.close();
});
it('old detections read as monitoring, water points get no line, and wind is not claimed at the point',()=>{
  const {dom,H}=load();
  const old=H.build({wind:wind(0,10),terrain:null,rate:forest,ageHours:50,kind:'unknown_forest',now:DAY});
  expect(old.line?.startsWith('ถ้ายังมีไฟ ให้เฝ้าระวัง:')).toBe(true);expect(old.line).not.toContain('ทิศที่ไฟอาจลาม');
  expect(old.details.join(' ')).toContain('ไม่ใช่ลม ณ จุดนี้');
  const water=H.build({wind:wind(0,10),terrain:null,rate:null,ageHours:2,kind:'water',now:DAY});
  expect(water.line).toBeNull();dom.window.close();
});
it('the map cone uses the same 24-hour freshness gate as the popup',()=>{
  const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
  expect(html).toContain('CmeSpreadHint.ageHours(h.detected_at)<=CmeSpreadHint.FRESH_HOURS');
  expect(html).not.toContain('2 + W.kmh*0.18');
});
it('the compact first-screen row keeps the cited range, the monitoring wording and the calm and water rules',()=>{
  const {dom,H}=load();
  const fresh=H.build({wind:wind(0,10),terrain:null,rate:forest,ageHours:3,kind:'unknown_forest',now:DAY}).short;
  expect(fresh.title).toBe('อาจลามไปทางใต้');expect(fresh.deg).toBe(180);
  expect(fresh.sub).toContain(`ถ้าเป็นป่าผลัดใบและยังไหม้อยู่ ราว ${forest.min_m_per_hour}–${forest.max_m_per_hour} ม. ใน 1 ชม.`);
  const old=H.build({wind:wind(0,10),terrain:null,rate:forest,ageHours:40,now:DAY}).short;
  expect(old.title).toBe('ถ้ายังมีไฟ ให้เฝ้าระวังทางใต้');expect(old.sub).not.toContain('ม. ใน 1 ชม.');
  const calm=H.build({wind:wind(0,1),terrain:null,rate:null,ageHours:2,now:DAY}).short;
  expect(calm.deg).toBeNull();expect(calm.title).toContain('ยังบอกทิศลามไม่ได้');
  const crop=H.build({wind:wind(0,10),terrain:null,rate:reference.spread_rates.crop,ageHours:2,now:DAY}).short;
  expect(crop.sub).not.toContain('ม. ใน 1 ชม.');
  expect(H.build({wind:wind(0,10),terrain:null,rate:null,ageHours:2,kind:'water',now:DAY}).short).toBeNull();
  dom.window.close();
});
