import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { JSDOM } from 'jsdom';
import { expect, it } from 'vitest';

const html = readFileSync(resolve(__dirname, '../index.html'), 'utf8');
const guide = new JSDOM(html).window.document.getElementById('guideview')!;

it('guide leads with 1362, then 4 short steps that each do the thing', () => {
  const first = guide.querySelector('.gd-v2')!.firstElementChild!;
  expect(first.matches('a.gd-sos[href="tel:1362"]')).toBe(true);
  const steps = [...guide.querySelectorAll('.guide-steps > li')];
  expect(steps.length).toBe(4);
  for (const step of steps) {
    expect(step.querySelectorAll('.gc-try').length).toBe(1);
    expect(step.querySelector('.gc-try')!.matches('[data-guide-try],[data-open-view],a[href^="tel:"]')).toBe(true);
    expect(step.querySelector('p')!.textContent!.length).toBeLessThanOrEqual(140);
  }
  // A hotspot is still never presented as a confirmed fire.
  expect(steps[0].textContent).toContain('ยังไม่ใช่ไฟที่ยืนยันแล้ว');
});

it('legend keeps the two dust scales apart and every caveat is still there', () => {
  const legend = guide.querySelector('.gd-legend')!.textContent!;
  expect(legend).toContain('µg/m³');
  expect(legend).toContain('AQI เกณฑ์ US EPA');
  expect(legend).toContain('ไม่ใช่การพยากรณ์ว่าไฟจะเกิดที่ไหน');
  const faq = guide.querySelector('.gd-faq')!.textContent!;
  expect(faq).toContain('การไม่พบหมุดก็ยังสรุปว่าไม่มีไฟไม่ได้');
  expect(faq).toContain('ไม่ได้แปลว่าฝุ่นเป็นศูนย์หรือปลอดภัย');
  // Expert material stays, at the end.
  const expert = guide.querySelector('.gd-expert')!;
  expect(expert.querySelector('#guideMethods')!.textContent).toContain('FWI');
  expect(expert.querySelector('#evidenceSources')).not.toBeNull();
  expect(guide.querySelector('.gd-v2')!.lastElementChild).toBe(expert);
});

it('both alert kinds say who can use them', () => {
  const alerts = [...guide.querySelectorAll('.gd-alert')].map(a => a.textContent!);
  expect(alerts[0]).toContain('ไม่ต้องสมัครสมาชิก');
  expect(alerts[1]).toContain('รอผู้ดูแลอนุมัติ');
});
