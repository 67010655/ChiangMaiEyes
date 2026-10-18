import {JSDOM} from 'jsdom';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {describe,it,expect} from 'vitest';
const source=readFileSync(resolve(__dirname,'../public/ventilation-ui.js'),'utf8');
function setup(){
  const dom=new JSDOM('<h2 id="ventilationHeading" tabindex="-1">GFS</h2><button id="ventilationLoad"></button><select id="ventilationLead"><option value="0">Now</option><option value="48">Later</option></select><div id="ventilationBody"></div><button id="gfsArchiveLoad"></button><select id="gfsArchiveDays"><option value="7">7 days</option></select><p id="gfsArchiveStatus"></p><ul id="gfsArchiveList"></ul>',{runScripts:'outside-only'});
  const w=dom.window as any;
  w.CmeEvidence={escapeHtml:(x:any)=>String(x).replace(/</g,'&lt;').replace(/>/g,'&gt;'),stamp:(x:any)=>String(x||'—')};
  w.eval(source);return dom;
}
const tick=()=>new Promise(r=>setTimeout(r,0));
describe('native NOAA model detail',()=>{
  it('keeps zero ventilation, missing values and model time distinct',()=>{
    const dom=setup(),w=dom.window as any;
    const result=w.CmeVentilation.render({cells:[{}],reference_cell:{latitude:18.75,longitude:99,pbl_height_m:20,wind_pbl_m_s:null,ventilation_rate_m2_s:0,wind_to_deg:null},valid_at:'<img onerror=x>',run_at:'2026-10-12',cycle_fallback:true});
    expect(result).toContain('0 <small>m²/s');expect(result).toContain('ยังไม่มีข้อมูล');
    expect(result).not.toContain('<img');expect(result).toContain('รอบใหม่ยังไม่ครบ');
    expect(result).toContain('คนละระดับกับลมสถานี');dom.window.close();
  });
  it('a late current forecast cannot replace a selected future frame',async()=>{
    const dom=setup(),w=dom.window as any,pending:any[]=[];
    w.fetchJson=(path:string)=>new Promise(resolve=>pending.push({path,resolve}));
    w.document.getElementById('ventilationLoad').click();
    const select=w.document.getElementById('ventilationLead');select.value='48';select.dispatchEvent(new w.Event('change'));
    pending[1].resolve({reference_cell:null});await tick();
    const text=w.document.getElementById('ventilationBody').textContent;
    pending[0].resolve({reference_cell:{},cells:[]});await tick();
    expect(w.document.getElementById('ventilationBody').textContent).toBe(text);
    expect(pending.map(p=>p.path)).toEqual(['/api/ventilation?lead_hours=0','/api/ventilation?lead_hours=48']);
    dom.window.close();
  });
  it('archive list omits invalid IDs, escapes source dates and an archived selection wins over pending live data',async()=>{
    const dom=setup(),w=dom.window as any,pending:any[]=[];
    w.fetchJson=(path:string)=>new Promise(resolve=>pending.push({path,resolve}));
    w.document.getElementById('gfsArchiveLoad').click();
    pending[0].resolve({total:2,first_stored_at:'2026-10-13',frames:[
      {id:'a'.repeat(64),valid_at:'<img onerror=x>',run_at:'2026-10-12',first_stored_at:'2026-10-13',forecast_hour:24,cell_count:104},
      {id:'../../secret',valid_at:'invalid'}]});await tick();
    const list=w.document.getElementById('gfsArchiveList');
    expect(list.querySelectorAll('button')).toHaveLength(1);expect(list.querySelector('img')).toBeNull();
    w.document.getElementById('ventilationLoad').click();
    list.querySelector('button').click();
    pending[2].resolve({first_stored_at:'2026-10-13',frame:{reference_cell:null}});await tick();
    const chosen=w.document.getElementById('ventilationBody').textContent;
    expect(chosen).toContain('กำลังดูรอบจากคลัง');
    expect(w.document.activeElement.id).toBe('ventilationHeading');
    pending[1].resolve({reference_cell:{},cells:[]});await tick();
    expect(w.document.getElementById('ventilationBody').textContent).toBe(chosen);
    expect(pending[2].path).toBe('/api/ventilation/archive/'+'a'.repeat(64));
    dom.window.close();
  });
  it('an empty archive does not imply historical coverage',async()=>{
    const dom=setup(),w=dom.window as any;
    w.fetchJson=async()=>({total:0,frames:[],first_stored_at:null});
    w.document.getElementById('gfsArchiveLoad').click();await tick();
    expect(w.document.getElementById('gfsArchiveStatus').textContent).toContain('ยังไม่มีรอบ');
    expect(w.document.getElementById('gfsArchiveList').children).toHaveLength(0);
    dom.window.close();
  });
});
