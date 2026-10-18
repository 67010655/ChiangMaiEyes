'use strict';
// Public snapshots loaded directly from the publisher; no media mirroring.
let publicCameras = [];
let cameraFetchStatus = 'loading';
let cameraPoll = null;
const cameraImageStates = new Map();
const cameraName = () => publicCameras[state.camera]?.name || 'กล้องสาธารณะเชียงใหม่';
const cameraTime = value => value ? new Date(value).toLocaleString('th-TH', {dateStyle:'medium',timeStyle:'medium',timeZone:'Asia/Bangkok'}) : 'ยังไม่มีข้อมูล';

function cameraFreshness(camera) {
  if (!camera?.imageUrl) return 'ยังไม่มีภาพให้แสดง';
  if (!camera.filenameTimestamp) return 'ต้นทางไม่ระบุเวลาไฟล์';
  if (new Date(camera.filenameTimestamp).getTime()>Date.now()+300000)return 'เวลาในชื่อไฟล์อยู่ในอนาคต · ต้องตรวจสอบ';
  const minutes = Math.max(0, Math.floor((Date.now()-new Date(camera.filenameTimestamp).getTime())/60000));
  return minutes > 30 ? `เวลาไฟล์เกิน 30 นาที · ${minutes} นาทีที่แล้ว` : `เวลาไฟล์ ${minutes} นาทีที่แล้ว`;
}

function renderPublicCameras() {
  const camera = publicCameras[state.camera];
  const imageState = cameraImageStates.get(camera?.id) || 'loading';
  const media = camera?.imageUrl
    ? `<img class="public-camera-image" data-public-camera="${esc(camera.id)}" src="${esc(camera.imageUrl)}" alt="ภาพกล้องสาธารณะ ${esc(camera.name)}" referrerpolicy="no-referrer"><div class="camera-image-status" role="status"><strong>${imageState==='error'?'ดูภาพจากต้นทางไม่ได้':imageState==='loaded'?'ภาพนิ่งจากกล้องสาธารณะ':'กำลังโหลดภาพจากต้นทาง'}</strong><small>${cameraFreshness(camera)}</small></div>`
    : `<div class="camera-state">${icon('camera')}<h2>${cameraFetchStatus==='loading'?'กำลังตรวจกล้องสาธารณะ':'ยังอ่านภาพกล้องไม่ได้'}</h2><p>เปิดเว็บต้นทางเพื่อตรวจสอบสถานะ หรือกดตรวจภาพล่าสุดอีกครั้ง</p></div>`;
  return `<section><div class="page-title"><div>${tag('กล้องสาธารณะ · เชียงใหม่')}<h1>มองเห็นพื้นที่ ผ่านกล้อง CCTV</h1><p>ภาพจริงจากกล้องติดตามแม่น้ำปิง เลือกจุดและตรวจเวลาในภาพก่อนใช้ประกอบสถานการณ์</p></div><a class="button light" href="#map">กลับไปแผนที่ ↗</a></div>${cameraFetchStatus==='error'?'<div class="notice amber" style="margin-bottom:20px"><b>ตรวจรายการล่าสุดไม่ได้</b>ภาพที่มีอาจเป็นข้อมูลจากครั้งก่อน โปรดดูเวลาและตรวจจากเว็บต้นทาง</div>':''}
  <div class="camera-layout"><div><div class="camera-viewer public-camera-viewer">${media}<div class="viewer-bottom"><span>${esc(camera?.id||'CCTV')} · ${esc(camera?.name||'กล้องเชียงใหม่')}</span><button data-action="camera-full" ${camera?.imageUrl?'':'disabled'}>ขยายภาพ ↗</button></div></div>
  <div class="public-camera-actions"><button data-public-action="refresh">ตรวจภาพล่าสุด ↻</button><a class="link" href="${esc(camera?.sourcePage||'https://appserv.net/pingriver.php')}" target="_blank" rel="noopener noreferrer">ดูเว็บต้นทาง ↗</a><span class="small">ภาพนิ่งเป็นช่วงเวลา · ไม่ใช่วิดีโอสดต่อเนื่อง</span></div></div>
  <aside class="camera-list">${publicCameras.map((c,i)=>`<button class="camera-choice ${state.camera===i?'active':''}" data-camera="${i}" aria-pressed="${state.camera===i}"><span class="camera-thumb public-camera-thumb">${icon('camera')}<small>${esc(c.id)}</small></span><span><strong>${esc(c.name)}</strong><small>${esc(c.district)}<br>${esc(cameraFreshness(c))}</small></span></button>`).join('')||'<div class="notice">กำลังอ่านรายชื่อกล้องสาธารณะ</div>'}<a class="button light small-button" href="#officer">ดูการจัดการกล้อง ↗</a></aside></div>
  <div class="camera-metadata"><div><small>แหล่งเผยแพร่ภาพ</small><b>${esc(camera?.publisher||'AppServ PingRiver')}</b></div><div><small>ตำแหน่งตามต้นทาง</small><b>${esc(camera?.district||'เชียงใหม่')}</b></div><div><small>เวลาที่ระบุในชื่อไฟล์ (ไทย)</small><b>${cameraTime(camera?.filenameTimestamp)}</b></div><div><small>ตรวจรายการจากต้นทางเมื่อ</small><b>${cameraTime(camera?.checkedAt)}</b></div></div>
  <div class="camera-info"><div class="notice"><b>เวลาไฟล์ กับเวลาบันทึกของกล้อง</b>เวลาข้างบนอ่านจากชื่อไฟล์ที่ต้นทางเผยแพร่ อาจต่างจากตัวเลขเวลาที่กล้องฝังในภาพ โปรดอ่านทั้งสองค่า การกดตรวจใหม่ไม่ยืนยันว่ากล้องบันทึกภาพใหม่แล้ว</div><div class="notice amber"><b>กล้องแม่น้ำไม่ได้ครอบคลุมป่าทุกแห่ง</b>ใช้ชุดนี้ดูสภาพพื้นที่และทดลองการดูภาพจริง ยังไม่เชื่อมกล้องกับป่าชุมชนหรือใช้ภาพยืนยันว่ามีไฟป่า ผู้เผยแพร่ระบุแหล่งข้อมูลชลประทาน ส่วนเจ้าของกล้องรายจุดยังต้องยืนยัน</div></div>
  <div class="section-head" style="margin-top:30px"><h2>พบสิ่งผิดปกติ ต้องตรวจสอบต่อ</h2><a class="link" href="#community">เปิดงานชุมชน ↗</a></div><div class="incident-steps"><div><span>1</span>อ่านเวลาจริงที่อยู่ในภาพและจุดที่กล้องมองเห็น</div><div><span>2</span>บันทึกชื่อกล้อง เวลา และสิ่งที่พบ</div><div><span>3</span>ตรวจสอบร่วมกับข้อมูลพื้นที่ก่อนสรุปเหตุ</div></div></section>`;
}

function updateCameraImageStatus(image, loaded) {
  const id = image.dataset.publicCamera;
  if (!id) return;
  cameraImageStates.set(id, loaded ? 'loaded' : 'error');
  const viewer=image.closest('.public-camera-viewer');
  if (!viewer) return;
  viewer.classList.toggle('image-failed', !loaded);
  const label=viewer.querySelector('.camera-image-status strong');
  if(label)label.textContent=loaded?'ภาพนิ่งจากกล้องสาธารณะ':'ดูภาพจากต้นทางไม่ได้';
}
document.addEventListener('load', event => {
  if(event.target.matches?.('[data-public-camera]'))updateCameraImageStatus(event.target,true);
},true);
document.addEventListener('error', event => {
  if(event.target.matches?.('[data-public-camera]'))updateCameraImageStatus(event.target,false);
},true);

function openPublicCameraFull() {
  const camera=publicCameras[state.camera];
  if (!camera?.imageUrl) return;
  openDialog(esc(camera.name),`<img class="public-full-image" src="${esc(camera.imageUrl)}" alt="ภาพ CCTV สาธารณะ ${esc(camera.name)}" referrerpolicy="no-referrer"><p style="margin-top:15px">ภาพจริงจาก ${esc(camera.publisher)} · ${esc(camera.id)}<br>เวลาจากชื่อไฟล์: ${cameraTime(camera.filenameTimestamp)}<br>ตรวจเวลาที่กล้องฝังในภาพประกอบด้วย</p><a class="link" href="${esc(camera.sourcePage)}" target="_blank" rel="noopener noreferrer">ดูที่มา ↗</a>`);
}

async function loadPublicCameras(manual=false) {
  const button=document.querySelector('[data-public-action="refresh"]');
  if(button){button.disabled=true;button.textContent='กำลังตรวจรายการ…'}
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),20000);
  try{
    const response=await fetch('/api/public-cameras',{signal:controller.signal,cache:'no-store'});
    if(!response.ok)throw new Error('metadata unavailable');
    const data=await response.json();
    if(!Array.isArray(data.cameras))throw new Error('invalid metadata');
    data.cameras.forEach(camera=>{
      if(publicCameras.find(old=>old.id===camera.id)?.imageUrl!==camera.imageUrl)cameraImageStates.delete(camera.id);
    });
    publicCameras=data.cameras;
    cameraFetchStatus='ready';
    document.querySelectorAll('[data-public-camera-count]').forEach(el=>el.textContent=publicCameras.filter(c=>c.imageUrl).length);
    state.camera=Math.min(state.camera,Math.max(0,publicCameras.length-1));
  }catch{
    cameraFetchStatus='error';
    if(manual)toast('อ่านรายการกล้องไม่ได้ · ภาพเดิมอาจไม่สะท้อนสถานการณ์ปัจจุบัน');
  }finally{
    clearTimeout(timeout);
    if(location.hash==='#cameras'&&state.forests.length){
      const scroll=window.scrollY;render();window.scrollTo({top:scroll,behavior:'instant'});
      document.querySelectorAll('[data-public-camera]').forEach(img=>{
        if(img.complete)updateCameraImageStatus(img,img.naturalWidth>0);
      });
    }
    if(button?.isConnected){button.disabled=false;button.textContent='ตรวจภาพล่าสุด ↻'}
  }
}
document.addEventListener('click',event=>{if(event.target.closest('[data-public-action="refresh"]'))loadPublicCameras(true)});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&cameraPoll){clearInterval(cameraPoll);cameraPoll=null}else if(!document.hidden)configureCameraPoll()});
function configureCameraPoll(){
  clearInterval(cameraPoll);cameraPoll=null;
  if(location.hash==='#cameras'&&!document.hidden)cameraPoll=setInterval(()=>loadPublicCameras(),60000);
}
window.addEventListener('hashchange',configureCameraPoll);
window.addEventListener('DOMContentLoaded',()=>{loadPublicCameras();configureCameraPoll()});
