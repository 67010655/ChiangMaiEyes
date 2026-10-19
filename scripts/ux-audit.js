/* UX audit probes for ChiangMaiEyes (docs/UX_REDESIGN.md).
 * Paste into the browser console on the live or QA site, then run e.g.
 *   await CmeUxAudit.page()            // first screen of the current view
 *   await CmeUxAudit.views()           // every overlay page
 *   await CmeUxAudit.hotspotPopups()   // every hotspot popup
 * Numbers to report before/after each fix: visible characters on the first
 * screen, total characters, controls, text under 12 px, and mono text. */
(function(root){
  'use strict';
  const visible=e=>{
    if(!e||!e.getBoundingClientRect)return false;
    const r=e.getBoundingClientRect();if(r.width<1||r.height<1)return false;
    const s=getComputedStyle(e);if(s.visibility==='hidden'||s.display==='none'||+s.opacity===0)return false;
    for(let p=e.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open&&e.tagName!=='SUMMARY')return false;
    return true;
  };
  const inView=e=>{if(!visible(e))return false;const r=e.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth;};
  const skip='script,style,.leaflet-marker-pane,.leaflet-control-attribution';
  function scope(rootEl=document.body,{firstScreen=true}={}){
    const vis=firstScreen?inView:visible;
    const out={chars:0,mono:0,controls:0,tiny:[],small:[],unnamed:0,english:{}};
    const w=document.createTreeWalker(rootEl,NodeFilter.SHOW_TEXT);
    while(w.nextNode()){
      const p=w.currentNode.parentElement;if(!p||p.closest(skip))continue;
      const s=w.currentNode.textContent.replace(/\s+/g,'');if(!s||!vis(p))continue;
      out.chars+=s.length;
      const cs=getComputedStyle(p);
      if(/mono/i.test(cs.fontFamily))out.mono+=s.length;
      if(parseFloat(cs.fontSize)<12&&out.tiny.length<10)out.tiny.push(cs.fontSize+' '+s.slice(0,24));
      (w.currentNode.textContent.match(/\b[A-Za-z][A-Za-z.]{2,}\b/g)||[]).forEach(x=>{out.english[x]=(out.english[x]||0)+1;});
    }
    rootEl.querySelectorAll('button,a[href],input,select,textarea,summary,[role=button]').forEach(c=>{
      if(!vis(c)||c.closest(skip))return;out.controls++;
      const name=(c.getAttribute('aria-label')||c.innerText||c.title||c.placeholder||'').trim();
      if(!name)out.unnamed++;
      const r=c.getBoundingClientRect();if((r.width<43.5||r.height<43.5)&&out.small.length<15)out.small.push(Math.round(r.width)+'x'+Math.round(r.height)+' '+name.slice(0,20));
    });
    out.english=Object.entries(out.english).sort((a,b)=>b[1]-a[1]).slice(0,15).map(([k,v])=>k+'×'+v).join(', ');
    return out;
  }
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  async function views(){
    const ids={analytics:'analytics',data:'dataview',report:'reportview',threed:'threedview',guide:'guideview'};
    const res={};
    for(const [k,id] of Object.entries(ids)){
      root.CmeNavigation.open(k);await wait(k==='threed'?5000:2000);
      const el=document.getElementById(id);
      res[k]={firstScreen:scope(el).chars,total:scope(el,{firstScreen:false}).chars,controls:scope(el,{firstScreen:false}).controls};
    }
    root.CmeNavigation.open('home');return res;
  }
  async function hotspotPopups(){
    const ms=root.layers.hotspots.getLayers(),rows=[];
    for(let i=0;i<ms.length;i++){
      root.map.closePopup();root.map.setView(ms[i].getLatLng(),11,{animate:false});await wait(250);
      ms[i].openPopup();await wait(1500);
      const c=document.querySelector('.leaflet-popup-content');if(!c){rows.push({i,error:'no popup'});continue;}
      const clone=c.cloneNode(true);
      clone.querySelectorAll('details').forEach(d=>[...d.childNodes].forEach(n=>{if(n.nodeName!=='SUMMARY')n.remove();}));
      rows.push({i,chars:clone.textContent.replace(/\s+/g,'').length,title:c.querySelector('.hs-title')?.textContent,scrolls:c.scrollHeight>c.clientHeight+4});
    }
    root.map.closePopup();return rows;
  }
  root.CmeUxAudit={scope,page:()=>scope(document.body),views,hotspotPopups};
})(window);
