import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { expect,test } from 'vitest';

const source=readFileSync(new URL('../public/terrain-ui.js',import.meta.url),'utf8');
const tick=()=>new Promise(r=>setTimeout(r,0));
function setup(){
  const dom=new JSDOM('<h2 id="forestTerrainHeading" tabindex="-1"></h2><select id="forestTerrainSelect"></select><button id="forestTerrainLoad"></button><div id="forestTerrainBody"></div>',{runScripts:'outside-only'});
  const w=dom.window as any;
  w.CmeEvidence={escapeHtml:(x:any)=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'),stamp:(x:any)=>String(x||'—')};
  w.eval(source);return dom;
}
const sample=(slope=20)=>({forest:{status:'available',slope_deg:{median:slope},elevation_m:{median:0},slope_valid_pixels:10,inside_pixels:10},metadata:{dataset:'Copernicus',release:'2021',vertical_reference:'EGM2008',grid_spacing_m:30,horizontal_crs:'EPSG:32647',slope_algorithm:'Horn 3x3',resampling:'bilinear',generated_at:'<img onerror=x>',attribution:'source',liability_notice:'source'}});

test('terrain retains real zero, missing geometry and units while escaping metadata',()=>{
  const dom=setup(),w=dom.window as any;
  const result=w.CmeTerrain.render(sample());expect(result).toContain('0 <small>m');expect(result).toContain('องศา');expect(result).not.toContain('<img');
  const missing=w.CmeTerrain.render({forest:{status:'boundary_needs_review'},metadata:{}});
  expect(missing).toContain('ต้องตรวจสอบ');expect(missing).not.toContain('0 <small>');dom.window.close();
});

test('native forest labels are safe and delayed old forests do not overwrite the selection',async()=>{
  const dom=setup(),w=dom.window as any,pending:any[]=[];
  w.CmeTerrain.setForests([{forest_id:'f1',name:'<img onerror=x>',amphoe:'district'},{forest_id:'f2',name:'Second'}]);
  expect(w.document.querySelector('img')).toBeNull();
  w.fetchJson=(path:string)=>new Promise(resolve=>pending.push({path,resolve}));
  const select=w.document.getElementById('forestTerrainSelect');select.value='f1';select.dispatchEvent(new w.Event('change'));
  select.value='f2';select.dispatchEvent(new w.Event('change'));
  pending[1].resolve(sample(35));await tick();const chosen=w.document.getElementById('forestTerrainBody').textContent;
  pending[0].resolve(sample(10));await tick();expect(w.document.getElementById('forestTerrainBody').textContent).toBe(chosen);
  expect(chosen).toContain('35');dom.window.close();
});

test('unknown composite risk is displayed as unavailable rather than zero or low risk',()=>{
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
  const fn=html.match(/function renderRiskScore\(\)\{[\s\S]*?\n\}/)![0];
  const dom=new JSDOM('<div id="riskScoreBlock"></div><svg><circle id="riskArc"></circle></svg><span id="riskScore"></span><span id="riskCategory"></span><div id="riskFactors"></div><p id="riskLiveNote"></p>',{runScripts:'outside-only'}),w=dom.window as any;
  w.currentDashboard={risk:{score:null,category:'ข้อมูลไม่ครบ'}};w.eval(fn);w.renderRiskScore();
  expect(w.document.getElementById('riskScore').textContent).toBe('—');
  expect(w.document.getElementById('riskCategory').textContent).toBe('ยังประเมินไม่ได้');dom.window.close();
});
