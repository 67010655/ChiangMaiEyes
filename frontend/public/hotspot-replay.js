/* Phase 4: replay the loaded hotspots over time (▶). Uses only the points the
 * page already has; while a replay is showing, the map is clearly labelled as
 * past data and closing it returns to the live view. */
(function(root){
  'use strict';
  const HOUR=3600000, STEP_H=1, PLAY_STEP_H=2, TICK_MS=300;
  // Bounds of the replay window: earliest detection (floored to the hour) to now.
  function windowFor(items,now=Date.now()){
    const ts=(items||[]).map(h=>Date.parse(h.detected_at)).filter(Number.isFinite);
    if(!ts.length)return null;
    const start=Math.floor(Math.min(...ts)/HOUR)*HOUR, end=Math.ceil(now/HOUR)*HOUR;
    return end>start?{start,end}:null;
  }
  // Points seen by time t (later detections are not shown yet).
  const visibleAt=(items,t)=>(items||[]).filter(h=>{const d=Date.parse(h.detected_at);return Number.isFinite(d)&&d<=t;});
  const fmt=t=>new Intl.DateTimeFormat('th-TH',{timeZone:'Asia/Bangkok',weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(t)+' น.';
  const days=w=>Math.max(1,Math.round((w.end-w.start)/(24*HOUR)));

  let el,btn,bar,slider,label,count,playBtn,timer=null,win=null,opts=null,at=null;
  function init(o){
    opts=o;el=document.getElementById(o.mountId||'hsReplay');if(!el)return;
    el.innerHTML=`<button type="button" class="hs-replay-start" aria-expanded="false" aria-controls="hsReplayBar">▶ ย้อนดู <span data-days></span></button>
      <div class="hs-replay-bar" id="hsReplayBar" role="group" aria-label="ย้อนดูจุดความร้อน" hidden>
        <p class="hs-replay-note">กำลังย้อนดู · ไม่ใช่สถานการณ์ตอนนี้</p>
        <div class="hs-replay-row">
          <button type="button" class="hs-replay-play" aria-label="หยุดชั่วคราว">❚❚</button>
          <input type="range" class="hs-replay-slider" aria-label="เลือกเวลา" step="1">
          <button type="button" class="hs-replay-close" aria-label="กลับไปดูข้อมูลล่าสุด">✕</button>
        </div>
        <p class="hs-replay-when"><strong data-when></strong> · <span data-count></span></p>
      </div>`;
    btn=el.querySelector('.hs-replay-start');bar=el.querySelector('.hs-replay-bar');
    slider=el.querySelector('.hs-replay-slider');label=el.querySelector('[data-when]');count=el.querySelector('[data-count]');playBtn=el.querySelector('.hs-replay-play');
    btn.onclick=start;el.querySelector('.hs-replay-close').onclick=stop;
    playBtn.onclick=()=>timer?pause():play();
    slider.oninput=()=>{pause();show(win.start+Number(slider.value)*HOUR);};
    el.addEventListener('keydown',e=>{if(e.key==='Escape'&&!bar.hidden){e.preventDefault();stop();}});
    refresh();
  }
  // Called when new data arrives; hides the button when there is nothing to replay.
  function refresh(){
    if(!el)return;
    const w=windowFor(opts.getItems());
    el.hidden=!w;
    if(w)el.querySelector('[data-days]').textContent=days(w)+' วัน';
    if(at!==null&&w){win=w;slider.max=String(Math.round((w.end-w.start)/HOUR));}
  }
  function show(t){
    at=Math.min(Math.max(t,win.start),win.end);
    slider.value=String(Math.round((at-win.start)/HOUR));
    label.textContent=fmt(at);
    count.textContent=visibleAt(opts.getItems(),at).length+' จุด';
    opts.onFrame(at);
  }
  function start(){
    win=windowFor(opts.getItems());if(!win)return;
    slider.min='0';slider.max=String(Math.round((win.end-win.start)/HOUR));
    btn.hidden=true;btn.setAttribute('aria-expanded','true');bar.hidden=false;
    document.body.classList.add('hs-replaying');
    show(win.start);
    if(root.matchMedia?.('(prefers-reduced-motion: reduce)').matches){pause();}else play();
    playBtn.focus({preventScroll:true});
  }
  function play(){
    if(at>=win.end)show(win.start);
    clearInterval(timer);
    timer=setInterval(()=>{if(at>=win.end){pause();return;}show(at+PLAY_STEP_H*HOUR);},TICK_MS);
    playBtn.textContent='❚❚';playBtn.setAttribute('aria-label','หยุดชั่วคราว');
  }
  function pause(){
    clearInterval(timer);timer=null;
    if(playBtn){playBtn.textContent='▶';playBtn.setAttribute('aria-label','เล่นต่อ');}
  }
  function stop(){
    pause();at=null;
    if(!bar)return;
    bar.hidden=true;btn.hidden=false;btn.setAttribute('aria-expanded','false');
    document.body.classList.remove('hs-replaying');
    opts.onFrame(null);
    btn.focus({preventScroll:true});
  }
  root.CmeHotspotReplay={init,refresh,stop,windowFor,visibleAt,current:()=>at,STEP_H};
})(window);
