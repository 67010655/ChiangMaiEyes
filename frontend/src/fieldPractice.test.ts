import {JSDOM} from 'jsdom';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {describe,it,expect} from 'vitest';

const sources=['decision-support.js','field-checks.js','practice-workspace.js'].map(p=>readFileSync(resolve(__dirname,'../public/'+p),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,0));
function page(){const dom=new JSDOM('<div id="host"></div>',{url:'https://example.test/',runScripts:'outside-only'});sources.forEach(s=>dom.window.eval(s));return dom;}
const iid='20000000-0000-4000-8000-000000000099',rid='40000000-0000-4000-8000-000000000099';
function fixture(){return {id:rid,version:1,data:{title:'<script>Fixture</script>',scenario:'offline',started_at:new Date().toISOString(),incidents:[],events:[],feedback:[]}};}

describe('field evidence exports and rehearsal UI boundaries',()=>{
  it('preserves unknown measurements and time delays as blanks, not zero',()=>{
    const dom=page(),w=dom.window as any;
    dom.window.document.getElementById('host')!.innerHTML=w.CmeField.form('check');
    expect((dom.window.document.querySelector('[name="checked_at"]') as HTMLInputElement).value).toBe('');
    (dom.window.document.querySelector('[data-field-now]') as HTMLButtonElement).click();
    const p=w.CmeField.payload(dom.window.document.getElementById('check'),iid);
    expect(p.latitude).toBeNull();expect(p.position_accuracy_m).toBeNull();expect(p.email_delivered_at).toBeNull();
    expect(p.checked_at.endsWith('+07:00')).toBe(true);
    expect(w.CmeField.delay(null,null)).toBe('');
    expect(w.CmeField.delay('2026-01-02T00:00:00Z','2026-01-01T00:00:00Z')).toBe('');
    expect(w.CmeField.delay('2026-01-01T00:00:00Z','2026-01-01T00:02:00Z')).toBe(120);
    dom.window.close();
  });
  it('escapes observation text and prevents spreadsheet formula injection',()=>{
    const dom=page(),w=dom.window as any;
    const checks=[{id:iid,data:{outcome:'unverified',method:'unavailable',note:'=HYPERLINK("https://example.test")',satellite_source:'<img onerror="alert(1)">',satellite_match:'not_checked'}}];
    const html=w.CmeField.list(checks);
    expect(html).not.toContain('<img');
    const csv=w.CmeField.csv(checks,{id:iid},'practice_only');
    expect(csv).toContain('practice_only');expect(csv).toContain("'=HYPERLINK");expect(csv).toContain('delivery_to_seen_seconds');
    dom.window.close();
  });
  it('keeps draft and request IDs through a simulated failed send, then submits only to practice',async()=>{
    const dom=page(),w=dom.window as any,calls:any[]=[];let run=fixture();
    const api=async(path:string,opt:any={})=>{calls.push({path,...opt});
      if(path==='/practice/runs'&&!opt.data)return [];
      if(path==='/practice/runs'&&opt.data)return structuredClone(run);
      if(path.endsWith('/actions')){run.version++;run.data.incidents.push({id:opt.data.incident_id,description:opt.data.note,status:'pending',observation:'smoke',coordinator:null,partner:null,linked_id:null,created_at:new Date().toISOString(),photos:[],checks:[],permissions:{read:true,manage:true,note:true}} as never);return structuredClone(run);}
      return structuredClone(run);
    };
    await w.CmePractice.attach(dom.window.document.getElementById('host'),{api});
    dom.window.document.getElementById('cpStart')!.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await tick();await tick();
    expect(dom.window.document.querySelector('script')).toBeNull();
    const field=dom.window.document.querySelector<HTMLTextAreaElement>('#cpCreate textarea')!;field.value='Fixture retained note';field.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
    (dom.window.document.querySelector('[data-cp="offline"]') as HTMLElement).click();
    dom.window.document.getElementById('cpCreate')!.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await tick();await tick();
    expect(dom.window.document.body.textContent).toContain('จำลองส่งสะดุด');
    expect(dom.window.document.querySelector<HTMLTextAreaElement>('#cpCreate textarea')!.value).toBe('Fixture retained note');
    expect(calls.filter(c=>c.path.endsWith('/actions'))).toHaveLength(0);
    dom.window.document.getElementById('cpCreate')!.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await tick();await tick();
    const send=calls.find(c=>c.path.endsWith('/actions'));
    expect(send.data.note).toBe('Fixture retained note');expect(send.data.incident_id).toMatch(/[a-f0-9-]{36}/);
    expect(calls.every(c=>c.path.startsWith('/practice/'))).toBe(true);
    expect(dom.window.document.querySelectorAll('#cpStatus-'+send.data.incident_id)).toHaveLength(1);
    w.CmePractice.reset();dom.window.close();
  });
  it('does not expose incident controls to an uninvited simulated role',async()=>{
    const dom=page(),w=dom.window as any;const run=fixture();
    const api=async(path:string,opt:any={})=>path==='/practice/runs'&&!opt.data?[]:structuredClone(run);
    await w.CmePractice.attach(dom.window.document.getElementById('host'),{api});
    dom.window.document.getElementById('cpStart')!.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await tick();await tick();
    const select=dom.window.document.getElementById('cpActor') as HTMLSelectElement;select.value='B';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}));await tick();await tick();
    expect(dom.window.document.getElementById('cpCreate')).toBeNull();expect(dom.window.document.body.textContent).toContain('ต้องได้รับคำเชิญ');
    w.CmePractice.reset();dom.window.close();
  });
});
