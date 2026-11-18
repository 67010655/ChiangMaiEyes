/* Coordinates line for every pin and hotspot: the numbers, a copy button and a Google Maps link,
   so anyone can paste the point into Google Maps or send it in LINE. */
(function(root){
  'use strict';
  const fmt=v=>Number(v).toFixed(5);
  function text(lat,lon){return `${fmt(lat)}, ${fmt(lon)}`;}
  function html(lat,lon){
    if(!Number.isFinite(Number(lat))||!Number.isFinite(Number(lon)))return '';
    const t=text(lat,lon);
    return `<p class="cme-coord"><span aria-hidden="true">📍</span> <b>${t}</b>`+
      `<button type="button" class="cme-coord-copy" data-coord="${t}">คัดลอก</button>`+
      `<a class="cme-coord-map" href="https://www.google.com/maps/search/?api=1&query=${fmt(lat)},${fmt(lon)}" target="_blank" rel="noopener">เปิดใน Google Maps</a></p>`;
  }
  async function copy(value){
    try{await root.navigator.clipboard.writeText(value);return true;}catch{}
    try{const t=root.document.createElement('textarea');t.value=value;t.setAttribute('readonly','');t.style.position='fixed';t.style.opacity='0';
      root.document.body.appendChild(t);t.select();const ok=root.document.execCommand('copy');t.remove();return ok;}catch{return false;}
  }
  // One handler for every popup, sheet and card, including ones drawn later.
  root.document.addEventListener('click',async e=>{
    const b=e.target.closest?.('.cme-coord-copy');if(!b)return;
    e.preventDefault();e.stopPropagation();
    const ok=await copy(b.dataset.coord);
    const old=b.textContent;b.textContent=ok?'คัดลอกแล้ว ✓':'คัดลอกไม่ได้';setTimeout(()=>{b.textContent=old;},1600);
  },true);
  root.CmeCoords={html,text,copy};
})(window);
