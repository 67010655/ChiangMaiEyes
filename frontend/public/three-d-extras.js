/* 3D view extras: district name labels and moving wind streaks, so the 3D
 * view reads like the 2D map. Wind uses the same Open-Meteo grid as the 2D
 * streamlines (leaflet-velocity format) and draws on one canvas — no DOM
 * markers per particle, which is what made earlier 3D wind pins stutter. */
(function(root){
  'use strict';
  // ---------- district labels ----------
  // Area-weighted centroid of the largest ring; good enough for a label.
  function ringCentroid(ring){
    let a=0,cx=0,cy=0;
    for(let i=0,j=ring.length-1;i<ring.length;j=i++){
      const [x0,y0]=ring[j],[x1,y1]=ring[i],f=x0*y1-x1*y0;a+=f;cx+=(x0+x1)*f;cy+=(y0+y1)*f;
    }
    if(!a){const n=ring.length||1;return ring.reduce((m,p)=>[m[0]+p[0]/n,m[1]+p[1]/n],[0,0]);}
    return [cx/(3*a),cy/(3*a)];
  }
  function ringArea(r){let a=0;for(let i=0,j=r.length-1;i<r.length;j=i++)a+=r[j][0]*r[i][1]-r[i][0]*r[j][1];return Math.abs(a/2);}
  function labelPoint(geometry){
    const polys=geometry.type==='Polygon'?[geometry.coordinates]:geometry.type==='MultiPolygon'?geometry.coordinates:[];
    let best=null;polys.forEach(p=>{const r=p[0];if(r&&(!best||ringArea(r)>ringArea(best)))best=r;});
    return best?ringCentroid(best):null;
  }
  const LABEL_MIN_Z=7.3, LABEL_MAX_Z=12.5;
  let labels=[], labelMap=null;
  function setDistrictLabels(map,districts){
    labels.forEach(m=>m.remove());labels=[];labelMap=map;
    if(!map||!root.maplibregl)return;
    districts.forEach(d=>{
      const pt=labelPoint(d.geometry);if(!pt)return;
      const el=document.createElement('span');el.className='td-dlabel';el.textContent=d.name;el.setAttribute('aria-hidden','true');
      labels.push(new root.maplibregl.Marker({element:el,anchor:'center'}).setLngLat(pt).addTo(map));
    });
    if(!map._cmeLabelZoom){map._cmeLabelZoom=true;map.on('zoomend',syncLabels);}
    syncLabels();
  }
  function syncLabels(){
    if(!labelMap)return;const z=labelMap.getZoom();
    const show=z>=LABEL_MIN_Z&&z<=LABEL_MAX_Z;
    labels.forEach(m=>m.getElement().classList.toggle('off',!show));
  }

  // ---------- wind streaks ----------
  function sampler(field){
    if(!Array.isArray(field)||field.length<2)return null;
    const h=field[0].header,U=field[0].data,V=field[1].data;
    const {nx,ny,lo1,la1,dx,dy}=h;
    const at=(c,r)=>{c=Math.max(0,Math.min(nx-1,c));r=Math.max(0,Math.min(ny-1,r));const i=r*nx+c;return [U[i],V[i]];};
    return (lon,lat)=>{
      const fc=(lon-lo1)/dx, fr=(la1-lat)/dy;
      if(fc<0||fr<0||fc>nx-1||fr>ny-1)return null;
      const c0=Math.floor(fc),r0=Math.floor(fr),tx=fc-c0,ty=fr-r0;
      const a=at(c0,r0),b=at(c0+1,r0),c=at(c0,r0+1),d=at(c0+1,r0+1);
      const mix=k=>(a[k]*(1-tx)+b[k]*tx)*(1-ty)+(c[k]*(1-tx)+d[k]*tx)*ty;
      const u=mix(0),v=mix(1);
      return Number.isFinite(u)&&Number.isFinite(v)?[u,v]:null;
    };
  }
  let W=null;
  function startWind(map,field,{bounds,light=false,mobile=false}={}){
    stopWind();
    const sample=sampler(field);
    if(!map||!sample||root.matchMedia?.('(prefers-reduced-motion: reduce)').matches)return false;
    const container=map.getCanvasContainer(), mapCanvas=map.getCanvas();
    const canvas=document.createElement('canvas');canvas.className='td-wind-canvas';canvas.setAttribute('aria-hidden','true');
    container.insertBefore(canvas,mapCanvas.nextSibling);
    const ctx=canvas.getContext('2d');
    const [west,south,east,north]=bounds||[97.9,17.1,99.7,20.3];
    const N=mobile?220:420, MAX_AGE=90;
    const spawn=p=>{p.lon=west+Math.random()*(east-west);p.lat=south+Math.random()*(north-south);p.age=Math.floor(Math.random()*MAX_AGE);p.px=null;return p;};
    const parts=Array.from({length:N},()=>spawn({}));
    const resize=()=>{const r=mapCanvas.getBoundingClientRect(),dpr=Math.min(2,root.devicePixelRatio||1);canvas.width=r.width*dpr;canvas.height=r.height*dpr;canvas.style.width=r.width+'px';canvas.style.height=r.height+'px';ctx.setTransform(dpr,0,0,dpr,0,0);};
    resize();
    const clear=()=>{ctx.clearRect(0,0,canvas.width,canvas.height);parts.forEach(p=>p.px=null);};
    const onMove=()=>clear();
    map.on('move',onMove);map.on('resize',resize);
    // Same wind colour as the 2D map: cyan on dark, deep teal on light.
    const ink=()=>document.body.classList.contains('light-mode')?'rgba(14,116,144,':'rgba(55,209,214,';
    let raf=0,last=0;
    const frame=now=>{
      raf=requestAnimationFrame(frame);
      if(now-last<33)return;last=now;            // ~30 fps is plenty for streaks
      if(document.hidden)return;
      // Fade old trails.
      ctx.globalCompositeOperation='destination-in';ctx.fillStyle='rgba(0,0,0,0.9)';ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.globalCompositeOperation='source-over';
      const z=map.getZoom(), step=0.0009*Math.pow(2,9-z);   // degrees per (m/s) per frame, constant on screen
      ctx.lineWidth=2;ctx.lineCap='round';
      for(const p of parts){
        const uv=sample(p.lon,p.lat);
        if(!uv||++p.age>MAX_AGE){spawn(p);p.age=0;continue;}
        const k=Math.cos(p.lat*Math.PI/180)||1;
        p.lon+=uv[0]*step/k;p.lat+=uv[1]*step;
        const pt=map.project([p.lon,p.lat]);
        if(p.px){
          const sp=Math.hypot(uv[0],uv[1]);
          ctx.strokeStyle=ink()+Math.min(.9,.58+sp/12).toFixed(2)+')';
          ctx.beginPath();ctx.moveTo(p.px.x,p.px.y);ctx.lineTo(pt.x,pt.y);ctx.stroke();
        }
        p.px=pt;
      }
    };
    raf=requestAnimationFrame(frame);
    W={map,canvas,stop:()=>{cancelAnimationFrame(raf);map.off('move',onMove);map.off('resize',resize);canvas.remove();}};
    return true;
  }
  function stopWind(){W?.stop();W=null;}
  root.CmeThreeDExtras={setDistrictLabels,syncLabels,startWind,stopWind,labelPoint,sampler,running:()=>!!W};
})(window);
