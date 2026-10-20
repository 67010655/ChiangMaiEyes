/* Supabase handles credentials and sessions. This module only controls the account UI. */
(function(root){
  'use strict';
  let context,busy=false,returning=false,returnTarget='#community';
  const cooldowns=new Map();
  const el=id=>document.getElementById(id);
  function errorText(error){
    const code=error?.code||'',message=String(error?.message||'');
    if(code==='invalid_credentials'||message==='Invalid login credentials')return 'อีเมลหรือรหัสผ่านไม่ถูกต้อง ลองอีกครั้งหรือรับลิงก์เข้าใช้ทางอีเมล';
    if(code==='email_not_confirmed')return 'บัญชีนี้ยังไม่ได้ยืนยันอีเมล ตรวจกล่องจดหมายหรือกดส่งอีเมลยืนยันใหม่';
    if(code==='otp_expired')return 'ลิงก์หรือรหัสหมดอายุแล้ว กรุณาขออีเมลใหม่และใช้ฉบับล่าสุด';
    if(code==='over_email_send_rate_limit'||code==='over_request_rate_limit'||error?.status===429)return 'ขออีเมลถี่เกินไป กรุณารอสักครู่แล้วลองใหม่';
    if(['email_address_not_authorized','email_provider_disabled','signup_disabled'].includes(code)||/smtp|not authorized|not allowed|error sending/i.test(message))return 'ระบบส่งอีเมลสำหรับบัญชีทั่วไปยังไม่พร้อม กรุณาติดต่อผู้ดูแล บัญชียังไม่ได้รับการยืนยัน';
    if(/fetch|network|connection/i.test(message)||root.navigator.onLine===false)return 'เชื่อมต่อไม่ได้ ตรวจอินเทอร์เน็ตแล้วลองอีกครั้ง';
    if(code==='user_already_exists')return 'ลองเข้าสู่ระบบด้วยบัญชีเดิม หรือรับลิงก์เข้าใช้ทางอีเมล';
    if(code==='weak_password')return 'รหัสผ่านยังไม่ผ่านเงื่อนไข กรุณาใช้รหัสผ่านที่ยาวและเดายากขึ้น';
    return 'ดำเนินการไม่สำเร็จ กรุณาลองใหม่ หากยังติดขัดให้ติดต่อผู้ดูแล';
  }
  function text(id,value){const node=el(id);if(node){node.textContent=value;node.style.display=value?'block':'none';}}
  function clearMessages(){['siErr','siMsg','suErr','suMsg'].forEach(id=>text(id,''));}
  function switchTab(tab){
    ['signin','signup'].forEach((name,index)=>{el(index?'authTabSignup':'authTabSignin').classList.toggle('active',tab===name);el(index?'authTabSignup':'authTabSignin').setAttribute('aria-selected',String(tab===name));el(index?'authFormSignup':'authFormSignin').style.display=tab===name?'block':'none';});
    el('authHeading').textContent=tab==='signup'?'สมัครสมาชิก':'เข้าสู่ระบบ';
  }
  function requestedTarget(){
    const match=root.location.hash.match(/^#community\/incident\/([a-f0-9-]{36})$/i),id=new URL(root.location.href).searchParams.get('incident');
    return match?'#community/incident/'+match[1]:/^[a-f0-9-]{36}$/i.test(id||'')?'#community/incident/'+id:null;
  }
  function open(){returnTarget=requestedTarget()||'#community';clearMessages();el('authModalBackdrop').classList.add('open');switchTab('signin');el('siEmail').focus();}
  function close(){
    el('authModalBackdrop').classList.remove('open');
    ['siPassword','siOtp','suPassword'].forEach(id=>{if(el(id))el(id).value='';});
    ['siPassword','suPassword'].forEach(id=>{const i=el(id);if(i&&i.type==='text'){i.type='password';const b=i.parentElement?.querySelector('.auth-eye');if(b){b.textContent='แสดง';b.setAttribute('aria-pressed','false');b.setAttribute('aria-label','แสดงรหัสผ่าน');}}});
  }
  async function run(prefix,task){
    if(busy)return;
    clearMessages();
    if(!context.client){text(prefix+'Err','ระบบบัญชียังโหลดไม่สำเร็จ กรุณาโหลดหน้าเว็บใหม่');return;}
    busy=true;
    const buttons=[...el('authModalBackdrop').querySelectorAll('button')];
    buttons.forEach(button=>button.disabled=true);
    el('authModalBackdrop').setAttribute('aria-busy','true');
    text(prefix+'Msg','กำลังดำเนินการ…');
    try{await task();}catch(error){text(prefix+'Msg','');text(prefix+'Err',errorText(error));}
    finally{busy=false;buttons.forEach(button=>button.disabled=false);el('authModalBackdrop').removeAttribute('aria-busy');}
  }
  function email(prefix){const input=el(prefix+'Email');return input.reportValidity()?input.value.trim():null;}
  function redirect(){return returnTarget.startsWith('#community/incident/')?root.location.origin+'/?incident='+returnTarget.split('/').pop():root.location.origin+'/#community';}
  function signedIn(){const target=returnTarget;close();setTimeout(()=>context.openCommunity(target),0);}
  async function signIn(event){
    event.preventDefault();const address=email('si');if(!address)return false;
    const password=el('siPassword').value;
    await run('si',async()=>{const {error}=await context.client.auth.signInWithPassword({email:address,password});if(error)throw error;signedIn();});return false;
  }
  async function signUp(event){
    event.preventDefault();const address=email('su');if(!address)return false;
    const name=el('suName').value.trim(),password=el('suPassword').value;
    await run('su',async()=>{
      const {data,error}=await context.client.auth.signUp({email:address,password,options:{data:{full_name:name},emailRedirectTo:redirect()}});
      el('suPassword').value='';if(error)throw error;
      if(data?.session){signedIn();return;}
      text('suMsg','ส่งคำขอสมัครแล้ว ตรวจอีเมลและจดหมายขยะเพื่อยืนยันบัญชี จากนั้นจึงขอสิทธิ์ป่าชุมชน หากมีบัญชีอยู่แล้วให้เข้าสู่ระบบ');
    });return false;
  }
  async function sendEmail(kind,prefix){
    const address=email(prefix);if(!address||busy)return;
    const key=kind+'/'+address.toLowerCase(),remaining=Math.ceil(((cooldowns.get(key)||0)-Date.now())/1000);
    if(remaining>0){text(prefix+'Err','รออีก '+remaining+' วินาทีก่อนขออีเมลใหม่');return;}
    await run(prefix,async()=>{
      const request=kind==='signup'?context.client.auth.resend({type:'signup',email:address,options:{emailRedirectTo:redirect()}})
        :context.client.auth.signInWithOtp({email:address,options:{shouldCreateUser:false,emailRedirectTo:redirect()}});
      const {error}=await request;if(error)throw error;
      cooldowns.set(key,Date.now()+60000);
      text(prefix+'Msg','ขออีเมลแล้ว ตรวจกล่องจดหมายและจดหมายขยะ ใช้ลิงก์หรือรหัสจากฉบับล่าสุด หากยังไม่มีบัญชีให้สมัครสมาชิกก่อน');
    });
  }
  async function verifyCode(){
    const address=email('si'),code=el('siOtp').value.trim();if(!address)return;
    if(!/^\d{6,12}$/.test(code)){text('siErr','กรอกรหัสครั้งเดียวจากอีเมลให้ครบ');return;}
    await run('si',async()=>{const {error}=await context.client.auth.verifyOtp({email:address,token:code,type:'email'});el('siOtp').value='';if(error)throw error;signedIn();});
  }
  function togglePassword(id,button){const input=el(id);if(!input)return;const show=input.type==='password';input.type=show?'text':'password';button.textContent=show?'ซ่อน':'แสดง';button.setAttribute('aria-pressed',String(show));button.setAttribute('aria-label',show?'ซ่อนรหัสผ่าน':'แสดงรหัสผ่าน');}
  function sessionChanged(session){if(returning&&session){returning=false;signedIn();}}
  function init(adapter){
    context=adapter;
    returnTarget=requestedTarget()||'#community';
    const url=new URL(root.location.href),hash=new URLSearchParams(url.hash.slice(1));
    returning=hash.has('access_token')||url.searchParams.has('code');
    const code=hash.get('error_code')||url.searchParams.get('error_code');
    if(code||hash.has('error')||url.searchParams.has('error')){
      ['error','error_code','error_description'].forEach(key=>url.searchParams.delete(key));url.hash='community';
      root.history.replaceState(null,'',url.pathname+url.search+url.hash);open();text('siErr',errorText({code:code||'otp_expired'}));
    }
    el('authModalBackdrop').addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();if(!busy)close();}
    });
  }
  root.CmeAuth={init,open,close,switchTab,signIn,signUp,sendLink:()=>sendEmail('login','si'),resendConfirmation:prefix=>sendEmail('signup',prefix),verifyCode,sessionChanged,errorText,togglePassword};
})(window);
