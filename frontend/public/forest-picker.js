/* A4: the ~677-option community-forest selects get a type-to-filter box
 * (name or district). The native <select> stays — it keeps its form name,
 * required rule and every existing script that reads or sets its value. */
(function(root){
  'use strict';
  const SELECTORS=['#cwRequestForest','#anForest','#exportForest','#forestTerrainSelect','#spreadWorkspace select[name="forest_id"]'];
  const MIN_OPTIONS=30;
  let pickers=0;
  // Thai text: case-insensitive, ignore spaces and the อ./อำเภอ prefix people may or may not type.
  const norm=s=>String(s||'').toLowerCase().replace(/อำเภอ|อ\./g,'').replace(/\s+/g,'');
  function enhance(sel){
    if(!sel||sel.dataset.forestPicker)return;
    sel.dataset.forestPicker='1';
    let all=null, filtering=false;
    const wrap=document.createElement('div');wrap.className='forest-picker';
    const input=document.createElement('input');
    input.type='search';input.className='forest-picker-input';input.placeholder='พิมพ์ชื่อป่าหรืออำเภอ';
    input.setAttribute('aria-label','ค้นหาป่าชุมชนตามชื่อหรืออำเภอ');input.autocomplete='off';
    if(sel.id)input.setAttribute('aria-controls',sel.id);
    const status=document.createElement('span');status.className='forest-picker-count';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    wrap.append(input,status);sel.before(wrap);
    // Keep each option's <optgroup>: other scripts check for the groups and rebuild the list
    // (wiping what the person typed) when they are missing.
    const snapshot=()=>{all=[...sel.options].map(o=>({value:o.value,text:o.textContent,group:o.parentElement?.tagName==='OPTGROUP'?o.parentElement.label:null}));};
    const rebuild=keep=>{
      const out=[],groups=new Map();
      for(const o of all){if(o.group!==null&&!groups.has(o.group)){const g=document.createElement('optgroup');g.label=o.group;groups.set(o.group,g);out.push(g);}}
      const top=[];keep.forEach(o=>{const opt=new Option(o.text,o.value);if(o.group===null)top.push(opt);else groups.get(o.group).append(opt);});
      sel.replaceChildren(...top,...out);
    };
    const sync=()=>{wrap.hidden=sel.options.length<MIN_OPTIONS&&!input.value;};
    // Other scripts rebuild the list (data arrives, theme of the page changes): start fresh.
    // MutationObserver callbacks run later, so our own filtering is dropped with takeRecords() below.
    const watcher=new MutationObserver(()=>{snapshot();input.value='';status.textContent='';sync();});
    watcher.observe(sel,{childList:true,subtree:true});
    input.addEventListener('input',()=>{
      if(!all)snapshot();
      const q=norm(input.value), current=sel.value;
      const keep=q?all.filter(o=>!o.value||o.value===current||norm(o.text).includes(q)):all;
      filtering=true;
      rebuild(keep);
      sel.value=current;
      // One match: pick it, the same as choosing it in the list.
      const real=keep.filter(o=>o.value);
      if(q&&real.length===1&&sel.value!==real[0].value){sel.value=real[0].value;sel.dispatchEvent(new Event('change',{bubbles:true}));}
      watcher.takeRecords();filtering=false;
      status.textContent=q?`พบ ${real.length} ป่า`:'';
    });
    snapshot();sync();
    // Same suggestion list as the map search: type part of a name, pick a district or forest.
    if(root.CmeMapSearch){
      const items=()=>{if(!all)snapshot();return all.filter(o=>o.value).map(o=>{
        const district=/^d:/.test(o.value),[name,sub]=String(o.text).split(' · ');
        return {kind:district?'district':'forest',name:district?name.replace(/^อ\.|\s*\(ทั้งอำเภอ\)$/g,''):name,sub:district?'ทั้งอำเภอ':(sub?(/^อ\./.test(sub)?sub:'อ.'+sub):''),ref:o.value};});};
      root.CmeMapSearch.init({input,items,listId:'fpList'+(++pickers),onPick:r=>{
        input.value='';status.textContent='';
        if(all&&sel.options.length!==all.length){filtering=true;rebuild(all);watcher.takeRecords();filtering=false;}
        sel.value=r.ref;sel.dispatchEvent(new Event('change',{bubbles:true}));
        input.value=r.kind==='district'?'อ.'+r.name:r.name;
      }});
      wrap.classList.add('has-suggest');
    }
  }
  function scan(){SELECTORS.forEach(s=>document.querySelectorAll(s).forEach(enhance));}
  scan();if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan);
  // The spread form is rendered later; look again at most once per 500 ms.
  let queued=false;
  new MutationObserver(()=>{if(queued)return;queued=true;setTimeout(()=>{queued=false;scan();},500);}).observe(document.body||document.documentElement,{childList:true,subtree:true});
  root.CmeForestPicker={enhance,norm};
})(window);
