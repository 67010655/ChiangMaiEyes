import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const asset=(name:string)=>readFileSync(resolve(__dirname,'../public',name),'utf8');
const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
function setup(body=''){
  const dom=new JSDOM(body,{runScripts:'outside-only'});
  dom.window.eval(asset('public-guidance.js'));
  dom.window.eval(asset('ux-foundation.js'));
  dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));
  return {dom,ux:(dom.window as any).CmeUx};
}

it('all five PM categories have distinct semantic colors and a text alternative',()=>{
  const {dom,ux}=setup();
  const values=[10,20,30,50,100];
  expect(new Set(values.map(v=>ux.category(v).token)).size).toBe(5);
  for(const v of values){
    const chip=ux.pmChip(v);
    expect(chip.textContent).toContain(ux.category(v).label);
    expect(chip.querySelector('[aria-hidden=true]')).not.toBeNull();
  }
  for(const v of [null,undefined,NaN,-1,''])expect(ux.pmChipHtml(v)).toBe('');
  dom.window.close();
});

it('disclosing an introductory caveat preserves its text and source link',()=>{
  const text='ยังไม่ยืนยันเหตุในพื้นที่ ข้อมูลดาวเทียมต้องตรวจสอบกับคนในชุมชน '.repeat(3);
  const {dom}=setup(`<section class="data-review"><p>${text}<a href="https://example.org/source">ต้นทาง</a></p></section>`);
  const details=dom.window.document.querySelector('details')!;
  expect(details.open).toBe(false);
  expect(details.querySelector('p')!.textContent).toBe(text+'ต้นทาง');
  expect(details.querySelector('a')!.href).toBe('https://example.org/source');
  dom.window.close();
});

it('native validation uses Thai and clears the error when the user corrects input',()=>{
  const {dom}=setup('<input id="email" type="email" required aria-describedby="help"><span id="help">คำอธิบายเดิม</span>');
  const input=dom.window.document.querySelector('input')!;
  input.value='broken';input.checkValidity();
  expect(input.validationMessage).toContain('กรุณากรอกอีเมล');
  expect(input.getAttribute('aria-describedby')).toBe('help email-error');
  expect(input.getAttribute('aria-invalid')).toBe('true');
  input.value='name@example.com';input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
  expect(input.checkValidity()).toBe(true);
  expect(dom.window.document.getElementById('email-error')).toBeNull();
  expect(input.getAttribute('aria-describedby')).toBe('help');
  dom.window.close();
});

it('popup padding counts only chrome overlapping its own map, including the bottom menu',()=>{
  const {dom,ux}=setup('<header class="topbar"></header><section class="public-brief"></section><nav class="navrail"></nav><div id="map"></div>');
  const rect=(top:number,bottom:number,width=375)=>({top,bottom,left:0,right:width,width,height:bottom-top});
  const set=(s:string,r:any)=>Object.defineProperty(dom.window.document.querySelector(s),'getBoundingClientRect',{value:()=>r,configurable:true});
  set('.topbar',rect(0,52));set('.public-brief',rect(52,210));set('.navrail',rect(760,812));
  const container=dom.window.document.getElementById('map')!;
  set('#map',rect(210,760));
  expect(ux.popupPadding({getContainer:()=>container}).topLeft).toEqual([12,12]);
  // A fullscreen map has the same header/cards drawn over it.
  set('#map',rect(0,812));
  const pad=ux.popupPadding({getContainer:()=>container});
  expect(pad.topLeft).toEqual([12,222]);expect(pad.bottomRight).toEqual([12,64]);
  dom.window.close();
});

it('empty states render untrusted text as text and offer a working next action',()=>{
  const {dom,ux}=setup();let clicked=false;
  const node=ux.empty({title:'ไม่มีข้อมูล',reason:'<img src=x onerror=alert(1)>',action:'ดูที่มา',onAction:()=>{clicked=true;}});
  expect(node.querySelector('img')).toBeNull();node.querySelector('button').click();expect(clicked).toBe(true);
  dom.window.close();
});

it('an async contextual caveat remains readable in one disclosure without replacing its node',async()=>{
  const {dom}=setup('<section id="dataview"></section>');
  const note=dom.window.document.createElement('p');note.className='evidence-note';
  note.textContent='ยังไม่ได้เลือกป่า ค่านี้เป็นข้อมูลภูมิประเทศ ไม่ใช่ปริมาณเชื้อเพลิงหรือคะแนนความเสี่ยง';
  dom.window.document.getElementById('dataview')!.append(note);
  await new Promise(r=>setTimeout(r,0));
  expect(note.closest('details')?.querySelector('summary')?.textContent).toContain('ที่มา');
  expect(dom.window.document.querySelector('details p')).toBe(note);
  note.textContent='ข้อความใหม่จากแหล่งข้อมูล';
  expect(dom.window.document.querySelector('details p')!.textContent).toBe('ข้อความใหม่จากแหล่งข้อมูล');
  dom.window.close();
});

it.each([
  ['<label>ชนิดเหตุ<select id="choice" required><option value="">เลือก</option><option value="fire">ไฟ</option></select></label>','เลือกชนิดเหตุก่อน'],
  ['<select id="choice" required aria-label="อำเภอ"><option value="">เลือก</option><option value="a">เมือง</option></select>','เลือกอำเภอก่อน'],
  ['<select id="choice" required data-required-message="เลือกป่าชุมชนก่อน"><option value="">เลือก</option><option value="a">ป่าทดสอบ</option></select>','เลือกป่าชุมชนก่อน'],
])('select errors name the missing choice and clear on change: %s',(markup,message)=>{
  const {dom}=setup(markup);const select=dom.window.document.querySelector('select')!;
  select.checkValidity();expect(select.validationMessage).toBe(message);
  expect(dom.window.document.getElementById('choice-error')!.textContent).toBe(message);
  select.selectedIndex=1;select.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
  expect(select.checkValidity()).toBe(true);expect(select.hasAttribute('aria-invalid')).toBe(false);
  dom.window.close();
});

it.each(['left','right'])('Escape closes the %s drawer and restores the outside trigger',(side)=>{
  const {dom}=setup('<button id="mobileLayersBtn">ชั้นข้อมูล</button><button id="tabletInsightsBtn">สรุปอากาศ</button><aside class="side left"></aside><aside class="side right"></aside><div id="mobileDrawerBackdrop"></div>');
  const win=dom.window as any;win.syncQuickLayers=()=>{};
  win.eval(html.slice(html.indexOf('let mobileDrawerOpener='),html.indexOf('// Four plain-language switches;')));
  const opener=dom.window.document.getElementById(side==='left'?'mobileLayersBtn':'tabletInsightsBtn')!;
  opener.focus();win.openMobileDrawer(side,opener);
  expect(dom.window.document.activeElement).toBe(dom.window.document.querySelector('.side.'+side));
  // Switch inside the sheet: closing still returns to the original trigger.
  win.openMobileDrawer(side==='left'?'right':'left');
  dom.window.document.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
  expect(dom.window.document.querySelector('.drawer-open')).toBeNull();
  expect(dom.window.document.activeElement).toBe(opener);dom.window.close();
});

it('the header is the single place for data age, online and offline (H11)',()=>{
  const {dom,ux}=setup('<span id="connectionStatus" class="is-live"></span><span id="publicBriefFreshness"></span><span id="headerFreshness"></span>');
  const win=dom.window as any;const at=new Date(Date.now()-12*60000).toISOString();
  win.receivedAt=()=>at;win.freshnessText=()=>'อัปเดต 12 นาทีที่แล้ว';
  win.eval(html.slice(html.indexOf('function tick(){'),html.indexOf('\nfunction stamp()')));
  win.tick();expect(dom.window.document.getElementById('headerFreshness')!.hidden).toBe(false);
  expect(dom.window.document.getElementById('headerFreshness')!.textContent).toBe('อัปเดต 12 นาทีที่แล้ว');
  dom.window.document.getElementById('connectionStatus')!.className='is-offline';win.tick();
  expect(dom.window.document.getElementById('headerFreshness')!.textContent).toBe('เชื่อมต่อไม่ได้ · ข้อมูลเมื่อ 12 นาทีที่แล้ว');
  expect(ux.offlineAge(new Date().toISOString())).toBe('ข้อมูลเมื่อสักครู่');
  expect(dom.window.document.getElementById('headerFreshness')!.hidden).toBe(false);
  expect(ux.offlineAge(null)).toBe('');expect(ux.offlineAge('invalid')).toBe('');dom.window.close();
});

it('foundation CSS and the anonymous font preconnection are in head exactly once',()=>{
  const dom=new JSDOM(html);
  expect(dom.window.document.querySelectorAll('link[href="/ux-foundation.css"]')).toHaveLength(1);
  expect(dom.window.document.head.querySelector('link[href="/ux-foundation.css"]')).not.toBeNull();
  const link=dom.window.document.head.querySelector('link[rel=preconnect][href="https://fonts.gstatic.com"]')!;
  expect(link.hasAttribute('crossorigin')).toBe(true);dom.window.close();
});

it('the card does not repeat the data age, and the dust tile takes the PCD colour (H11)',()=>{
  const css=readFileSync(resolve(__dirname,'../public/topbar.css'),'utf8');
  expect(css).toMatch(/#publicBriefFreshness\{display:none!important\}/);
  expect(css).toContain(".public-signal.pm.has-level{background:var(--tile-level)!important}");
  expect(css).toMatch(/prefers-reduced-motion:reduce\)\{\.public-signal\.air>svg\{animation:none/);
  expect(html.indexOf('/topbar.css')).toBeGreaterThan(html.indexOf('/ux-foundation.css'));
  expect(html.indexOf('/topbar.css')).toBeLessThan(html.indexOf('</head>'));
});
