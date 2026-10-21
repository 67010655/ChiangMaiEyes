/* Map search: suggestions while typing (any part of the name: "แม่" finds
 * every place containing แม่), grouped as district / tambon / community
 * forest, keyboard and touch friendly. An empty box rotates example names
 * and, when focused, offers the districts with hotspots in the last 24 h. */
(function(root){
  'use strict';
  const MAX=40, HINT_MS=2600;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm=s=>String(s||'').toLowerCase().replace(/ป่าชุมชน|อำเภอ|ตำบล|อ\.|ต\./g,'').replace(/\s+/g,'');
  const svg=d=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">${d}</svg>`;
  const KIND={
    district:{label:'อำเภอ',group:'อำเภอ',ic:svg('<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z"/><path d="M9 4v14M15 6v14"/>')},
    tambon:{label:'ตำบล',group:'ตำบล',ic:svg('<path d="M12 21s-6-5.3-6-10a6 6 0 1 1 12 0c0 4.7-6 10-6 10Z"/><circle cx="12" cy="11" r="2.2"/>')},
    forest:{label:'ป่าชุมชน',group:'ป่าชุมชน',ic:svg('<path d="M12 3l6 8h-3l4 6h-6v4h-2v-4H5l4-6H6z"/>')},
  };

  // items: [{kind,name,sub,key,ref}] — built lazily from the page's data.
  function rank(items,q){
    const n=norm(q);if(!n)return [];
    const scored=[];
    for(const it of items){
      const k=it.key||(it.key=norm(it.name+' '+(it.sub||'')));
      const nameKey=it.nameKey||(it.nameKey=norm(it.name));
      const i=nameKey.indexOf(n),j=i<0?k.indexOf(n):i;
      if(j<0)continue;
      // Starts-with beats contains; districts before tambons before forests; shorter names first.
      scored.push([({district:0,tambon:1,forest:2}[it.kind])*10+(i===0?0:i>0?1:2),nameKey.length,it]);
    }
    scored.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    // A cap per group, so a common word ("แม่") still shows forests too.
    const cap={district:25,tambon:15,forest:20},seen={},out=[];let more=0;
    for(const [, ,it] of scored){seen[it.kind]=(seen[it.kind]||0)+1;if(seen[it.kind]<=cap[it.kind])out.push(it);else more++;}
    out.more=more;return out;
  }
  function listHtml(rows,q,title){
    if(!rows.length)return q?`<li class="ms-empty" role="option" aria-disabled="true">ไม่พบ "${esc(q)}" ลองพิมพ์บางส่วนของชื่อ หรือพิกัด เช่น 18.79, 98.98</li>`:'';
    const mark=t=>{const n=String(q||'').trim();if(!n)return esc(t);const i=t.indexOf(n);return i<0?esc(t):esc(t.slice(0,i))+'<mark>'+esc(t.slice(i,i+n.length))+'</mark>'+esc(t.slice(i+n.length));};
    let last='';
    return (title?`<li class="ms-title" role="presentation">${esc(title)}</li>`:'')+rows.map((r,i)=>{
      const head=!title&&r.kind!==last?`<li class="ms-title" role="presentation">${esc(KIND[r.kind].group)}</li>`:'';last=r.kind;
      return head+`<li role="option" id="msOpt${i}" class="ms-opt" data-i="${i}" aria-selected="${i===0}"><span class="ms-ic ${r.kind}" aria-hidden="true">${KIND[r.kind].ic}</span><span class="ms-t"><b>${mark(r.name)}</b><small>${esc(r.sub||KIND[r.kind].label)}${r.extra?' · '+esc(r.extra):''}</small></span></li>`;}).join('')+(rows.more?`<li class="ms-empty" role="presentation">และอีก ${rows.more} รายการ พิมพ์ให้เจาะจงขึ้นเพื่อดู</li>`:'');
  }

  function init({input,items,suggest,onPick,onCoordinates}){
    if(!input)return;
    const box=input.closest('.map-search')||input.parentElement;
    const list=document.createElement('ul');
    list.className='ms-list';list.id='mapSearchList';list.setAttribute('role','listbox');list.hidden=true;
    box.appendChild(list);
    input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls',list.id);input.setAttribute('aria-expanded','false');
    let rows=[],active=0;
    const show=(html,r)=>{rows=r;active=0;list.innerHTML=html;list.hidden=!html;input.setAttribute('aria-expanded',String(!!html));input.setAttribute('aria-activedescendant',r.length?'msOpt0':'');};
    const hide=()=>{list.hidden=true;input.setAttribute('aria-expanded','false');};
    const refresh=()=>{
      const q=input.value.trim();
      if(!q){const s=suggest?suggest():[];show(listHtml(s,'',s.length?'มีจุดความร้อนใน 24 ชม.':''),s);return;}
      if(/^\s*-?\d+(?:\.\d+)?[,\s]+-?\d+(?:\.\d+)?\s*$/.test(q)){show(`<li class="ms-opt" role="option" data-coord="1" aria-selected="true"><span class="ms-ic" aria-hidden="true">🧭</span><span class="ms-t"><b>${esc(q)}</b><small>ไปที่พิกัดนี้</small></span></li>`,[]);return;}
      const r=rank(items(),q);show(listHtml(r,q),r);
    };
    const choose=i=>{
      if(list.querySelector('[data-coord]')){hide();onCoordinates?.(input.value.trim());input.blur();return;}
      const r=rows[i];if(!r)return;hide();input.value=r.name;input.blur();onPick(r);
    };
    const move=d=>{
      const opts=[...list.querySelectorAll('.ms-opt')];if(!opts.length)return;
      active=(active+d+opts.length)%opts.length;
      opts.forEach((o,i)=>o.setAttribute('aria-selected',String(i===active)));
      input.setAttribute('aria-activedescendant',opts[active].id||'');opts[active].scrollIntoView?.({block:'nearest'});
    };
    input.addEventListener('input',refresh);
    input.addEventListener('focus',()=>{stopHints();refresh();});
    input.addEventListener('click',()=>{if(list.hidden)refresh();});
    input.addEventListener('keydown',e=>{
      if(e.key==='ArrowDown'){e.preventDefault();move(1);}
      else if(e.key==='ArrowUp'){e.preventDefault();move(-1);}
      else if(e.key==='Enter'){e.preventDefault();if(!list.hidden&&list.querySelector('.ms-opt'))choose(active);}
      else if(e.key==='Escape'){hide();input.blur();}
    });
    // pointerdown (not click) so the pick lands before the input blurs.
    list.addEventListener('pointerdown',e=>{const o=e.target.closest('.ms-opt');if(!o)return;e.preventDefault();choose(Number(o.dataset.i||0));});
    input.addEventListener('blur',()=>setTimeout(()=>{hide();if(!input.value)startHints();},150));

    // Rotating example names while the box is empty: a district, then a forest.
    const base=input.getAttribute('placeholder')||'';
    let timer=null,turn=0;
    function startHints(){
      stopHints();
      if(root.matchMedia?.('(prefers-reduced-motion: reduce)').matches)return;
      timer=setInterval(()=>{
        if(input.value||document.activeElement===input)return;
        const all=items(),pool=all.filter(it=>it.kind===(turn%2?'forest':'district'));turn++;
        const it=pool[Math.floor(Math.random()*pool.length)];
        if(it)input.setAttribute('placeholder',`ลองค้นหา "${it.kind==='forest'?(it.short||it.name):'อ.'+it.name}"`);
      },HINT_MS);
    }
    function stopHints(){if(timer)clearInterval(timer);timer=null;input.setAttribute('placeholder',base);}
    startHints();
    return {refresh,hide};
  }
  root.CmeMapSearch={init,rank,norm,listHtml};
})(typeof window!=='undefined'?window:globalThis);
