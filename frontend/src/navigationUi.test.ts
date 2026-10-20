import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { expect,test } from 'vitest';

const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const navigation=readFileSync(new URL('../public/navigation-ui.js',import.meta.url),'utf8');

test('four task menus preserve secondary features and keep the guide instructional',()=>{
  const dom=new JSDOM(html),d=dom.window.document;
  expect([...d.querySelectorAll('.nav-item')].map(el=>(el as HTMLElement).dataset.view)).toEqual(['home','analytics','community','guide']);
  const guide=d.getElementById('guideview')!;
  expect(guide.querySelectorAll('.guide-steps>li')).toHaveLength(4);
  expect(guide.querySelector('#guideReferences a,#evidenceSources')).not.toBeNull();
  for(const id of ['forestTerrainSelect','archiveControls','cameraViewer','fieldEvaluationPanel'])expect(guide.querySelector(`#${id}`)).toBeNull();
  expect(d.querySelector('#dataview #forestTerrainSelect')).not.toBeNull();
  expect(d.querySelector('#dataview #archiveBackfill')).not.toBeNull();
  // Public cameras were removed (D1, 19 Oct 2026): no page and no way back to it.
  expect(d.getElementById('cameraview')).toBeNull();
  expect(d.querySelector('[data-open-view="threed"]')).not.toBeNull();
  expect(d.querySelector('#analytics [data-open-view="report"]')).not.toBeNull();
  const ids=[...d.querySelectorAll('[id]')].map(el=>el.id);
  expect(ids.length).toBe(new Set(ids).size);
  dom.window.close();
});

test('mouse and keyboard journeys use the correct parent and close the previous view',()=>{
  const dom=new JSDOM(html,{runScripts:'outside-only'}),w=dom.window as any,d=w.document;
  const ids={analytics:'analytics',data:'dataview',report:'reportview',threed:'threedview',guide:'guideview'};
  w.eval(navigation);
  w.CmeNavigation.init({close:()=>Object.values(ids).forEach(id=>d.getElementById(id).classList.remove('open')),views:Object.fromEntries(['home',...Object.keys(ids)].map(view=>[view,()=>{if(ids[view as keyof typeof ids])d.getElementById(ids[view as keyof typeof ids]).classList.add('open');}]))});
  d.querySelector('.nav-item[data-view="analytics"]').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  d.querySelector('#analytics [data-open-view="data"]').click();
  expect(d.querySelectorAll('.open')).toHaveLength(1);
  expect(d.getElementById('dataview').classList.contains('open')).toBe(true);
  expect(d.querySelector('.nav-item[aria-current="page"]').dataset.view).toBe('analytics');
  w.CmeNavigation.open('threed');
  expect(d.getElementById('dataview').classList.contains('open')).toBe(false);
  expect(d.querySelector('.nav-item[aria-current="page"]').dataset.view).toBe('home');
  w.CmeNavigation.open('report');
  expect(d.getElementById('threedview').classList.contains('open')).toBe(false);
  expect(d.getElementById('reportview').classList.contains('open')).toBe(true);
  expect(d.querySelector('.nav-item[aria-current="page"]').dataset.view).toBe('analytics');
  w.CmeNavigation.open('cameras');
  expect(d.getElementById('reportview').classList.contains('open')).toBe(true);
  dom.window.close();
});
