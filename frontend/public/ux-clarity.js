/* Hidden view panels must not receive keyboard focus. Full-page views keep
   the header and navigation reachable; they are not modal dialogs. */
(() => {
  const panels=[...document.querySelectorAll('#analytics,#guideview,#dataview,#reportview,#phaseview,#threedview,#communityview')];
  const home=[...document.querySelectorAll('.mapwrap,.side,.public-brief')];
  let current=null;
  for(const panel of panels){
    const title=panel.querySelector('.ttl,h2,h3');
    if(title){
      title.id=title.id||`viewHeading-${panel.id}`;
      title.setAttribute('role','heading');title.setAttribute('aria-level','2');title.tabIndex=-1;
      panel.setAttribute('role','region');panel.setAttribute('aria-labelledby',title.id);
    }
    panel.querySelectorAll('svg.chart').forEach(svg=>{
      svg.setAttribute('role','img');
      svg.setAttribute('aria-label',svg.closest('.an-panel,.block')?.querySelector('h2,h3')?.textContent.trim()||'กราฟข้อมูล');
    });
  }
  // Titles change after an archive range loads; keep each chart's accessible
  // name in the same window without observing its own aria-label attribute.
  document.querySelectorAll('.an-panel,.side .block').forEach(group=>{
    const heading=group.querySelector('h2,h3'),svg=group.querySelector('svg.chart');
    if(!heading||!svg)return;
    const label=()=>{svg.setAttribute('role','img');svg.setAttribute('aria-label',heading.textContent.trim());};
    new MutationObserver(label).observe(heading,{childList:true,subtree:true,characterData:true});
    label();
  });
  function sync(){
    const open=panels.find(p=>p.classList.contains('open'))||null;
    panels.forEach(p=>{p.inert=p!==open;p.setAttribute('aria-hidden',String(p!==open));});
    home.forEach(el=>{el.inert=Boolean(open);});
    if(open!==current){
      const previous=current;current=open;
      if(open){
        const target=open.querySelector('.ttl,h2,h3,button');
        // Account dialogs own their focus while open.
        if(!document.querySelector('#authModalBackdrop.open'))target?.focus({preventScroll:true});
      }else if(previous&&(previous.contains(document.activeElement)||document.activeElement===document.body)){
        document.querySelector('.nav-item[aria-current="page"]')?.focus({preventScroll:true});
      }
    }
  }
  const observer=new MutationObserver(sync);
  panels.forEach(p=>observer.observe(p,{attributes:true,attributeFilter:['class']}));
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape'||event.defaultPrevented||!current)return;
    if(document.querySelector('.cme-modal-backdrop.open'))return;
    const close=current.querySelector('.an-close,.gd-close,.rp-close,.td-close,#phaseClose,#communityClose');
    if(close){event.preventDefault();close.click();document.querySelector('.nav-item[data-view="home"]')?.focus();}
  });
  sync();
})();

(() => {
  const backdrops=[...document.querySelectorAll('.cme-modal-backdrop')];
  let active=null,lastOutside=document.activeElement,returnTo=null;
  const restored=new Map();
  document.addEventListener('focusin',event=>{
    if(!backdrops.some(b=>b.contains(event.target)))lastOutside=event.target;
  });
  function sync(){
    const open=backdrops.find(b=>b.classList.contains('open'))||null;
    backdrops.forEach(b=>{b.inert=b!==open;b.setAttribute('aria-hidden',String(b!==open));});
    if(open===active)return;
    const old=active;active=open;
    restored.forEach((value,node)=>{node.inert=value;});restored.clear();
    if(open){
      returnTo=lastOutside;
      const dialog=open.querySelector('.cme-modal');
      dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');
      const heading=dialog.querySelector('h2,h3');
      if(heading){heading.id=heading.id||`dialogHeading-${open.id}`;dialog.setAttribute('aria-labelledby',heading.id);}
      open.querySelector('.close-x')?.setAttribute('aria-label','ปิดหน้าต่างนี้');
      [...document.body.children].forEach(node=>{
        if(node===open||node.contains(open)||['SCRIPT','STYLE','LINK'].includes(node.tagName))return;
        restored.set(node,node.inert);node.inert=true;
      });
      if(!open.contains(document.activeElement))open.querySelector('button,input,select,textarea')?.focus();
    }else if(old&&(old.contains(document.activeElement)||document.activeElement===document.body))returnTo?.focus?.({preventScroll:true});
  }
  document.addEventListener('keydown',event=>{
    if(!active||event.defaultPrevented)return;
    if(event.key==='Escape'){
      if(active.getAttribute('aria-busy')!=='true'){
        event.preventDefault();active.querySelector('.close-x')?.click();
      }
    }else if(event.key==='Tab'){
      const controls=[...active.querySelectorAll('button,a[href],input,select,textarea,[tabindex]')]
        .filter(el=>!el.disabled&&el.tabIndex>=0&&el.getClientRects().length>0);
      if(!controls.length){event.preventDefault();return;}
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    }
  });
  const observer=new MutationObserver(sync);
  backdrops.forEach(b=>observer.observe(b,{attributes:true,attributeFilter:['class']}));
  sync();
})();
