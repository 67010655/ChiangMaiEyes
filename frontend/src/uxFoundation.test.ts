import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const asset=(name:string)=>readFileSync(resolve(__dirname,'../public',name),'utf8');
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
