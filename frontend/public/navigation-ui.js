/* Navigation follows people's tasks; secondary views share a primary menu. */
(() => {
  const parents={threed:'home',data:'analytics',report:'analytics',phase:'community'};
  let config;
  function open(view,target){
    if(!config?.views[view])return;
    config.close();
    const parent=parents[view]||view;
    document.querySelectorAll('.nav-item').forEach(item=>{
      const active=item.dataset.view===parent;
      item.classList.toggle('active',active);
      if(active)item.setAttribute('aria-current','page');else item.removeAttribute('aria-current');
    });
    // The analytics sub-pages share one tab row; mark the page that is open.
    document.querySelectorAll('.workspace-links [data-open-view]').forEach(b=>{if(b.dataset.openView===view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    config.views[view]();
    if(target){
      const heading=document.getElementById(target);if(!heading)return;
      for(let node=heading.parentElement;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
      heading.tabIndex=-1;heading.focus({preventScroll:true});
      requestAnimationFrame(()=>heading.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}));
    }
  }
  function init(options){
    config=options;
    document.querySelectorAll('.nav-item').forEach(item=>{
      item.onclick=()=>open(item.dataset.view);
      item.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();item.click();}};
    });
    document.addEventListener('click',event=>{
      const button=event.target.closest?.('[data-open-view]');
      if(button)open(button.dataset.openView,button.dataset.openTarget);
    });
  }
  window.CmeNavigation={init,open};
})();
