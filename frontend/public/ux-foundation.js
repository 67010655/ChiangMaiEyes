/* Shared presentation only. No changes to observations, permissions or models. */
(function(root){
  'use strict';
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tokens=['--pm-very-good','--pm-good','--pm-moderate','--pm-unhealthy','--pm-hazardous'];
  const icons=['✓','✓','!','!','!!'];
  function category(value){
    const level=root.CmePublicGuidance.pmLevel(value);
    if(!level)return null;
    const i=root.CmePublicGuidance.PM_LEVELS.findIndex(l=>l.label===level.label);
    return {...level,token:tokens[i],icon:icons[i]};
  }
  function pmColor(value){const l=category(value);return getComputedStyle(document.documentElement).getPropertyValue(l?.token||'--state-old').trim();}
  function pmChipHtml(value){
    const l=category(value);return l?`<span class="cme-level" style="--level-color:var(${l.token})"><span class="cme-level-icon" aria-hidden="true">${l.icon}</span><span>${esc(l.label)}</span></span>`:'';
  }
  function pmChip(value){const box=document.createElement('span');box.innerHTML=pmChipHtml(value);return box.firstElementChild;}
  function empty({title,reason,action,onAction}){
    const node=document.createElement('span');node.className='cme-empty';
    const strong=document.createElement('strong');strong.textContent=title;node.append(strong);
    const why=document.createElement('small');why.textContent=reason;node.append(why);
    if(action){const button=document.createElement('button');button.type='button';button.textContent=action;button.addEventListener('click',onAction);node.append(button);}
    return node;
  }
  function toast(message){
    let node=document.getElementById('cme-toast');
    if(!node){node=document.createElement('div');node.id='cme-toast';node.className='cme-toast';node.setAttribute('role','status');node.setAttribute('aria-live','polite');document.body.append(node);}
    clearTimeout(toast.timer);node.textContent=String(message);node.hidden=false;
    toast.timer=setTimeout(()=>{node.hidden=true;},4000);
  }
  const mapLocale={
    'NavigationControl.ZoomIn':'ขยายแผนที่','NavigationControl.ZoomOut':'ย่อแผนที่',
    'NavigationControl.ResetBearing':'ลากเพื่อหมุนแผนที่ กดเพื่อหันทิศเหนือ',
    'Map.Title':'แผนที่เชียงใหม่','Map.Description':'ใช้ลูกศรเพื่อเลื่อนแผนที่ ใช้ปุ่มบวกหรือลบเพื่อปรับขนาด',
    'FullscreenControl.Enter':'เปิดเต็มหน้าจอ','FullscreenControl.Exit':'ออกจากเต็มหน้าจอ',
    'GeolocateControl.FindMyLocation':'ตำแหน่งของฉัน','GeolocateControl.LocationNotAvailable':'อ่านตำแหน่งไม่ได้',
    'AttributionControl.ToggleAttribution':'แสดงแหล่งที่มาของแผนที่','AttributionControl.MapFeedback':'แจ้งปัญหาแผนที่',
    'Popup.Close':'ปิดรายละเอียดจุด','Marker.Title':'ตำแหน่งบนแผนที่','LogoControl.Title':'โลโก้ MapLibre',
    'ScaleControl.Meters':'ม.','ScaleControl.Kilometers':'กม.','ScaleControl.Feet':'ฟุต','ScaleControl.Miles':'ไมล์','ScaleControl.NauticalMiles':'ไมล์ทะเล',
    'GlobeControl.Enable':'เปิดมุมมองโลก','GlobeControl.Disable':'ปิดมุมมองโลก','TerrainControl.Enable':'เปิดภูมิประเทศ','TerrainControl.Disable':'ปิดภูมิประเทศ',
    'CooperativeGesturesHandler.WindowsHelpText':'กด Ctrl พร้อมเลื่อนเมาส์เพื่อซูมแผนที่',
    'CooperativeGesturesHandler.MacHelpText':'กด ⌘ พร้อมเลื่อนเมาส์เพื่อซูมแผนที่',
    'CooperativeGesturesHandler.MobileHelpText':'ใช้สองนิ้วเพื่อเลื่อนแผนที่'
  };
  function popupPadding(map){
    const r=map.getContainer().getBoundingClientRect();let top=12,bottom=12;
    document.querySelectorAll('.topbar,.public-brief,.public-brief-details:not([hidden])').forEach(el=>{
      const b=el.getBoundingClientRect();if(b.width&&b.height&&b.top<=r.top+top&&b.bottom>r.top)top=Math.max(top,b.bottom-r.top+12);
    });
    const nav=document.querySelector('.navrail')?.getBoundingClientRect();
    if(nav?.width>r.width*.5&&nav.top>r.top&&nav.top<r.bottom)bottom=r.bottom-nav.top+12;
    return {topLeft:[12,top],bottomRight:[12,bottom],height:Math.max(60,r.height-top-bottom-65)};
  }
  if(root.L){
    root.L.Control.Zoom.mergeOptions({zoomInTitle:'ขยายแผนที่',zoomOutTitle:'ย่อแผนที่'});
    // Applies to every bindPopup, direct L.popup, and embedded Leaflet map.
    root.L.Popup.include({_adjustPan:function(){
      if(!this._map||!this._container||!this.options.autoPan)return;
      const map=this._map,p=popupPadding(map);
      this.options.autoPanPaddingTopLeft=root.L.point(p.topLeft);
      this.options.autoPanPaddingBottomRight=root.L.point(p.bottomRight);
      this._container.style.setProperty('--cme-popup-room',p.height+'px');
      // A disclosure or Thai font can resize content during Leaflet's animated
      // pan. Use the rendered rectangle and a single immediate pan, avoiding
      // competing animations with stale cached container heights.
      map._panAnim?.stop();
      const box=map.getContainer().getBoundingClientRect(),r=this._container.getBoundingClientRect();
      if(!box.width||!box.height)return;
      let dx=Math.max(0,r.right-(box.right-p.bottomRight[0]));
      let dy=Math.max(0,r.bottom-(box.bottom-p.bottomRight[1]));
      if(r.left-dx<box.left+p.topLeft[0])dx=r.left-box.left-p.topLeft[0];
      if(r.top-dy<box.top+p.topLeft[1])dy=r.top-box.top-p.topLeft[1];
      if(Math.abs(dx)>.75||Math.abs(dy)>.75){map.fire('autopanstart');map.panBy([dx,dy],{animate:false});}
    }});
    root.L.Map.addInitHook(function(){
      let observer;
      this.on('popupopen',e=>{
        observer?.disconnect();
        const close=e.popup.getElement().querySelector('.leaflet-popup-close-button');
        if(close){close.setAttribute('aria-label','ปิดรายละเอียดจุด');close.title='ปิดรายละเอียดจุด';}
        if(root.ResizeObserver){observer=new ResizeObserver(()=>{if(e.popup.isOpen())e.popup._adjustPan();});observer.observe(e.popup.getElement());}
        requestAnimationFrame(()=>{if(e.popup.isOpen())e.popup._adjustPan();});
      });
      this.on('popupclose',()=>observer?.disconnect());
      this.on('resize',()=>this._popup?._adjustPan());
      this.on('moveend',()=>requestAnimationFrame(()=>this._popup?._adjustPan()));
      // Header wrapping changes the map height without a window resize.
      if(root.ResizeObserver){const sizeObserver=new ResizeObserver(()=>{this.invalidateSize({pan:false});this._popup?._adjustPan();});sizeObserver.observe(this.getContainer());this.on('unload',()=>sizeObserver.disconnect());}
    });
  }
  function invalidMessage(input){
    const v=input.validity;
    if(v.valueMissing){
      if(input.tagName==='SELECT'){
        if(input.dataset.requiredMessage)return input.dataset.requiredMessage;
        const labelText=node=>{
          const copy=node.cloneNode(true);copy.querySelectorAll('input,select,textarea,[aria-hidden=true]').forEach(el=>el.remove());
          return copy.textContent.trim();
        };
        const labelled=(input.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)).filter(Boolean).map(labelText).join(' ');
        const label=labelled||input.getAttribute('aria-label')||[...(input.labels||[])].map(labelText).join(' ')||input.querySelector('option[value=""]')?.textContent||'';
        const subject=label.replace(/^(กรุณา)?เลือก\s*/, '').replace(/[\s*…\.]+$/g,'').replace(/ก่อน$/,'').trim();
        return subject?'เลือก'+subject+'ก่อน':'กรุณาเลือกตัวเลือกในช่องนี้';
      }
      return 'กรุณากรอกข้อมูลช่องนี้';
    }
    if(v.typeMismatch)return input.type==='email'?'กรุณากรอกอีเมลให้ครบ เช่น name@example.com':'กรุณากรอกข้อมูลให้ตรงรูปแบบ';
    if(v.rangeUnderflow)return 'กรุณากรอกค่าอย่างน้อย '+input.min;
    if(v.rangeOverflow)return 'กรุณากรอกค่าไม่เกิน '+input.max;
    if(v.tooShort)return 'กรุณากรอกอย่างน้อย '+input.minLength+' ตัวอักษร';
    return 'กรุณาตรวจรูปแบบข้อมูลช่องนี้';
  }
  // One note per field. Fields without an id get their own, so two of them
  // in a form never share (and overwrite) one message.
  let errSeq=0;
  const errorId=input=>(input.id||(input.dataset.cmeErrId||=('cme-field-'+(++errSeq))))+'-error';
  document.addEventListener('invalid',event=>{
    const input=event.target;if(!input.matches('input,select,textarea'))return;
    input.setCustomValidity(invalidMessage(input));input.setAttribute('aria-invalid','true');
    const id=errorId(input);let note=document.getElementById(id);
    if(!note){note=document.createElement('span');note.className='cme-field-error';note.id=id;input.after(note);}
    note.textContent=input.validationMessage;note.setAttribute('role','alert');
    input.setAttribute('aria-describedby',[...new Set((input.getAttribute('aria-describedby')||'').split(' ').filter(Boolean).concat(id))].join(' '));
  },true);
  function clearFieldError(event){
    const input=event.target;if(!input.matches('input,select,textarea'))return;
    input.setCustomValidity('');input.removeAttribute('aria-invalid');
    const id=errorId(input);document.getElementById(id)?.remove();
    input.setAttribute('aria-describedby',(input.getAttribute('aria-describedby')||'').split(' ').filter(s=>s!==id).join(' '));
  }
  document.addEventListener('input',clearFieldError);
  document.addEventListener('change',clearFieldError);
  document.addEventListener('keydown',event=>{
    if(event.defaultPrevented||event.key!=='Escape'||document.querySelector('.cme-modal-backdrop.open'))return;
    if(document.querySelector('.side.drawer-open')){event.preventDefault();root.closeMobileDrawers?.();return;}
    const panel=document.getElementById('publicBriefDetails');
    if(panel&&!panel.hidden){event.preventDefault();root.toggleBriefDetails?.();document.getElementById('publicBriefToggle')?.focus();}
  });
  function offlineAge(at,now=Date.now()){
    const time=Date.parse(at);if(!Number.isFinite(time))return '';
    const minutes=Math.max(0,Math.floor((now-time)/60000));
    return minutes<1?'ข้อมูลเมื่อสักครู่':'ข้อมูลเมื่อ '+(minutes<60?minutes+' นาที':Math.floor(minutes/60)+' ชั่วโมง')+'ที่แล้ว';
  }
  function setup(){
    const toast=document.getElementById('toast');if(toast){toast.setAttribute('role','status');toast.setAttribute('aria-live','polite');}
    // Preserve every word/link, disclose long introductory caveats in all reading views.
    const disclose=note=>{
      if(note.closest('details')||(note.textContent.length<80&&!(note.textContent.length>=30&&/ไม่ใช่|ยังไม่/.test(note.textContent))))return;
      const details=document.createElement('details');details.className='cme-source';
      const summary=document.createElement('summary');summary.textContent='ⓘ ที่มาและข้อควรรู้';details.append(summary);
      note.before(details);const body=document.createElement('div');details.append(body);body.append(note);
    };
    document.querySelectorAll('.workspace-intro,.data-review>p,.an-panel>.hint,.cw-auth-wall>p,#analytics .evidence-note,#dataview .evidence-note,#phaseview .evidence-note').forEach(disclose);
    // Some contextual notes arrive with an API response after initial render.
    // Only inspect newly inserted notes in reading views, never map popups or
    // print content, and keep the original node so updates/listeners survive.
    document.querySelectorAll('#analytics,#dataview,#phaseview').forEach(view=>{
      new MutationObserver(rows=>rows.forEach(row=>row.addedNodes.forEach(node=>{
        if(node.nodeType!==1)return;
        if(node.matches('.evidence-note'))disclose(node);
        node.querySelectorAll('.evidence-note').forEach(disclose);
      }))).observe(view,{childList:true,subtree:true});
    });
    document.querySelectorAll('.mobile-drawer-handle').forEach(handle=>{
      handle.setAttribute('role','button');handle.tabIndex=0;handle.setAttribute('aria-label','ปิดแผง หรือลากลงเพื่อปิด');
      const close=()=>root.closeMobileDrawers?.();let start;
      handle.addEventListener('click',close);
      handle.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();close();}});
      handle.addEventListener('pointerdown',e=>{start=e.clientY;handle.setPointerCapture(e.pointerId);});
      handle.addEventListener('pointerup',e=>{if(start!==undefined&&e.clientY-start>60)close();start=undefined;});
    });
    document.querySelectorAll('.close-x').forEach(b=>{b.setAttribute('aria-label','ปิดหน้าต่าง');b.type='button';});
    const detail=document.querySelector('.detail .empty');
    if(detail){detail.replaceChildren(empty({title:'รายละเอียดจุดบนแผนที่',reason:'เลือกจุดความร้อนเพื่อดูเวลา พื้นที่ และช่องทางติดต่อ',action:'กลับไปดูแผนที่',onAction:()=>root.closeMobileDrawers?.()}));}
  }
  root.CmeUx={category,pmColor,pmChip,pmChipHtml,empty,toast,popupPadding,mapLocale,invalidMessage,offlineAge};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})(window);
