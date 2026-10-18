import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createContext,runInContext} from 'node:vm';
import {JSDOM} from 'jsdom';
import {describe,it,expect} from 'vitest';
const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
const keyboard=readFileSync(resolve(__dirname,'../public/ux-clarity.js'),'utf8');

describe('public data clarity and keyboard navigation',()=>{
  it('ranks only recent satellite counts and escapes district names',()=>{
    const dom=new JSDOM(html);
    const ctx=createContext({document:dom.window.document,
      hotspots:[{district:'A',recent:true},{district:'A',recent:true},{district:'B',recent:false},{district:'<b>',recent:true}],
      isActiveHotspot:(h:any)=>h.recent,normalizeDistrictName:(n:string)=>n,
      CmeEvidence:{escapeHtml:(s:string)=>s.replace(/</g,'&lt;').replace(/>/g,'&gt;')}});
    runInContext(html.slice(html.indexOf('function rankList(){'),html.indexOf('//  ALERTS',html.indexOf('function rankList(){'))).replace(/\/\/ =+\s*$/, ''),ctx);
    runInContext('rankList()',ctx);
    const text=dom.window.document.getElementById('rankList')!.textContent!;
    expect(text).toContain('2 จุด');expect(text).not.toContain('B');
    expect(dom.window.document.querySelector('#rankList b')).toBeNull();
    dom.window.close();
  });
  it('unknown and zero scores are distinct',()=>{
    const ctx=createContext({});
    const start=html.indexOf('function experimentalScore('),end=html.indexOf('// =',start);
    runInContext(html.slice(start,end),ctx);
    expect(runInContext('experimentalScore(null)',ctx)).toBe('—');
    expect(runInContext('experimentalScore(0)',ctx)).toBe('0');
    expect(runInContext('experimentalScore(NaN)',ctx)).toBe('—');
  });
  it('opens the view at its heading, excludes hidden views and returns focus on Escape',async()=>{
    const dom=new JSDOM('<button class="nav-item" data-view="home" aria-current="page">Home</button><main class="mapwrap"><button>Map</button></main><div id="analytics"><h2>Analysis</h2><button class="an-close">Close</button></div><div id="guideview"><h2>Data</h2></div>');
    const doc=dom.window.document,panel=doc.getElementById('analytics')!;
    doc.querySelector('.an-close')!.addEventListener('click',()=>panel.classList.remove('open'));
    const ctx=createContext({document:doc,MutationObserver:dom.window.MutationObserver});
    runInContext(keyboard,ctx);
    expect((panel as any).inert).toBe(true);
    panel.classList.add('open');await new Promise(r=>setTimeout(r,0));
    expect((panel as any).inert).toBe(false);
    expect((doc.querySelector('.mapwrap') as any).inert).toBe(true);
    expect(doc.activeElement!.textContent).toBe('Analysis');
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    await new Promise(r=>setTimeout(r,0));
    expect(panel.classList.contains('open')).toBe(false);
    expect(doc.activeElement!.textContent).toBe('Home');
    expect((doc.querySelector('.mapwrap') as any).inert).toBe(false);
    dom.window.close();
  });
  it('keeps Tab inside a dialog and restores the button that opened it',async()=>{
    const dom=new JSDOM('<button id="trigger">Open</button><div class="cme-modal-backdrop" id="testDialog"><div class="cme-modal"><h3>Dialog</h3><button class="close-x">Close</button><input id="last"></div></div>');
    const doc=dom.window.document,backdrop=doc.getElementById('testDialog')!;
    // JSDOM has no layout; these controls are visible in the fixture.
    doc.querySelectorAll('button,input').forEach(el=>Object.defineProperty(el,'getClientRects',{value:()=>[{}]}));
    doc.querySelector('.close-x')!.addEventListener('click',()=>{
      backdrop.classList.remove('open');(doc.activeElement as HTMLElement).blur();
    });
    runInContext(keyboard,createContext({document:doc,MutationObserver:dom.window.MutationObserver}));
    (doc.getElementById('trigger') as HTMLElement).focus();backdrop.classList.add('open');
    await new Promise(r=>setTimeout(r,0));
    expect(doc.activeElement!.textContent).toBe('Close');
    (doc.getElementById('last') as HTMLElement).focus();
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));
    expect(doc.activeElement!.textContent).toBe('Close');
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
    await new Promise(r=>setTimeout(r,0));
    expect(backdrop.classList.contains('open')).toBe(false);
    expect(doc.activeElement!.id).toBe('trigger');
    dom.window.close();
  });
});
