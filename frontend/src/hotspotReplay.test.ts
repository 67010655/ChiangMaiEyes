import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const source = readFileSync(resolve(__dirname, '../public/hotspot-replay.js'), 'utf8');
const items = [
  { detected_at: '2026-10-15T06:05:00Z' },
  { detected_at: '2026-10-17T10:00:00Z' },
  { detected_at: '2026-10-19T07:14:00Z' },
];
function setup(list: any[] = items) {
  const dom = new JSDOM('<div id="hsReplay" hidden></div>', { runScripts: 'outside-only' });
  const w = dom.window as any; w.matchMedia = () => ({ matches: true }); // reduced motion: no autoplay timer
  w.eval(source);
  const frames: (number | null)[] = [];
  w.CmeHotspotReplay.init({ mountId: 'hsReplay', getItems: () => list, onFrame: (t: number | null) => frames.push(t) });
  return { dom, w, R: w.CmeHotspotReplay, frames };
}

it('shows only points detected by the chosen moment', () => {
  const { dom, R } = setup();
  expect(R.visibleAt(items, Date.parse('2026-10-17T12:00:00Z'))).toHaveLength(2);
  expect(R.visibleAt(items, Date.parse('2026-10-15T00:00:00Z'))).toHaveLength(0);
  const w = R.windowFor(items, Date.parse('2026-10-19T08:30:00Z'));
  expect(new Date(w.start).toISOString()).toBe('2026-10-15T06:00:00.000Z');
  expect(new Date(w.end).toISOString()).toBe('2026-10-19T09:00:00.000Z');
  dom.window.close();
});

it('labels the past clearly and returns to live data on close', () => {
  const { dom, w, R, frames } = setup();
  const root = w.document.getElementById('hsReplay');
  expect(root.hidden).toBe(false);
  root.querySelector('.hs-replay-start').click();
  expect(root.querySelector('.hs-replay-bar').hidden).toBe(false);
  expect(root.querySelector('.hs-replay-note').textContent).toContain('ไม่ใช่สถานการณ์ตอนนี้');
  expect(w.document.body.classList.contains('hs-replaying')).toBe(true);
  expect(R.current()).not.toBeNull();
  root.querySelector('.hs-replay-close').click();
  expect(R.current()).toBeNull();
  expect(frames.at(-1)).toBeNull();
  expect(w.document.body.classList.contains('hs-replaying')).toBe(false);
  dom.window.close();
});

it('hides the button when there is nothing to replay', () => {
  const { dom, w } = setup([]);
  expect(w.document.getElementById('hsReplay').hidden).toBe(true);
  dom.window.close();
});
