import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const w = new JSDOM('', { runScripts: 'outside-only' }).window as any;
w.eval(readFileSync(resolve(__dirname, '../public/satellite-passes.js'), 'utf8'));
const bkk = (hhmm: string) => new Date(`2026-10-22T${hhmm}:00+07:00`);

it('names the next pass in Bangkok time, wrapping past midnight', () => {
  expect(w.CmeSatPasses.short(bkk('18:00'))).toBe('ดาวเทียมรอบหน้าราว 01:00 น.');
  expect(w.CmeSatPasses.short(bkk('03:00'))).toBe('ดาวเทียมรอบหน้าราว 13:00 น.');
  expect(w.CmeSatPasses.short(bkk('00:10'))).toBe('ดาวเทียมรอบหน้าราว 01:00 น.');
});

it('during a pass, says when it reaches the map instead', () => {
  expect(w.CmeSatPasses.short(bkk('13:30'))).toBe('ดาวเทียมกำลังผ่าน · ขึ้นแผนที่ราว 17:30 น.');
  expect(w.CmeSatPasses.short(bkk('01:30'))).toBe('ดาวเทียมกำลังผ่าน · ขึ้นแผนที่ราว 05:30 น.');
});

it('the long text explains the gap and puts what people see first', () => {
  const t = w.CmeSatPasses.long(bkk('18:00'));
  expect(t).toContain('01:00–02:30 และ 13:00–14:30');
  expect(t).toContain('ราว 3 ชม.');
  expect(t).toContain('ขึ้นแผนที่ราว 05:30');
  expect(t).toContain('เชื่อสิ่งที่เห็น');
});
