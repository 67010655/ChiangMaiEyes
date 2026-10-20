import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { JSDOM } from 'jsdom';
import { expect, it } from 'vitest';

const html = readFileSync(resolve(__dirname, '../index.html'), 'utf8');
const guide = new JSDOM(html).window.document.getElementById('guideview')!;

it('guide opens with short cards, each with one button that does the thing', () => {
  const cards = [...guide.querySelectorAll('.guide-cards .guide-card')];
  expect(cards.length).toBe(6);
  for (const card of cards) {
    const buttons = card.querySelectorAll('button');
    expect(buttons.length).toBe(1);
    expect(buttons[0].textContent).toBe('ลองใช้เลย');
    expect(buttons[0].matches('[data-guide-try],[data-open-view]')).toBe(true);
    expect(card.querySelector('p')!.textContent!.length).toBeLessThanOrEqual(110);
  }
  // A hotspot is still never presented as a confirmed fire.
  expect(cards[1].textContent).toContain('ยังไม่ใช่ไฟที่ยืนยันแล้ว');
});

it('keeps the full step-by-step caveats behind a disclosure, not deleted', () => {
  const more = guide.querySelector('details.guide-more')!;
  expect(more).not.toBeNull();
  expect(more.textContent).toContain('การไม่พบหมุดก็ยังสรุปว่าไม่มีไฟไม่ได้');
  expect(more.querySelectorAll('.guide-steps li').length).toBe(4);
});
