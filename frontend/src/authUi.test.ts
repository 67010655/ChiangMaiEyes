import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

const html=readFileSync(resolve(__dirname,'../index.html'),'utf8');
const markup=html.slice(html.indexOf('<div class="cme-modal-backdrop" id="authModalBackdrop">'),html.indexOf('<!-- Manual hotspot report modal'));
const script=readFileSync(resolve(__dirname,'../public/auth-ui.js'),'utf8');
function setup(url='https://fixture.example/'){
  const dom=new JSDOM(markup,{url,runScripts:'outside-only'}),w=dom.window as any;
  const auth={signInWithPassword:vi.fn(async(_input:any)=>({data:{session:{}},error:null})),signUp:vi.fn(async(_input:any)=>({data:{session:null},error:null})),
    signInWithOtp:vi.fn(async(_input:any)=>({error:null})),resend:vi.fn(async(_input:any)=>({error:null})),verifyOtp:vi.fn(async(_input:any)=>({error:null}))};
  const opened=vi.fn();w.eval(script);w.CmeAuth.init({client:{auth},openCommunity:opened});
  for(const id of ['siEmail','suEmail'])w.document.getElementById(id).value='fixture@example.test';
  w.document.getElementById('suName').value='Fixture user';w.document.getElementById('suPassword').value='fixture-password-only';
  return {dom,w,auth,opened};
}
describe('account onboarding and recovery',()=>{
  it('requests signup confirmation at the community route without claiming area approval',async()=>{
    const {dom,w,auth}=setup();await w.CmeAuth.signUp({preventDefault(){}});
    expect(auth.signUp.mock.calls[0][0]).toMatchObject({options:{emailRedirectTo:'https://fixture.example/#community',data:{full_name:'Fixture user'}}});
    expect(w.document.getElementById('suMsg').textContent).toContain('ยืนยันบัญชี');
    expect(w.document.getElementById('suPassword').value).toBe('');dom.window.close();
  });
  it('requests a passwordless link without requiring or creating a new account',async()=>{
    const {dom,w,auth}=setup();await w.CmeAuth.sendLink();
    expect(auth.signInWithOtp.mock.calls[0][0]).toMatchObject({options:{shouldCreateUser:false}});
    expect(auth.signInWithPassword).not.toHaveBeenCalled();dom.window.close();
  });
  it('resends signup confirmation and prevents immediately repeating the same request',async()=>{
    const {dom,w,auth}=setup();await w.CmeAuth.resendConfirmation('su');await w.CmeAuth.resendConfirmation('su');
    expect(auth.resend).toHaveBeenCalledTimes(1);expect(auth.resend.mock.calls[0][0]).toMatchObject({type:'signup'});
    expect(w.document.getElementById('suErr').textContent).toContain('วินาที');dom.window.close();
  });
  it('explains sender restrictions and does not display successful signup after failure',async()=>{
    const {dom,w,auth}=setup();auth.signUp.mockResolvedValueOnce({data:null,error:{code:'email_address_not_authorized'}} as any);
    await w.CmeAuth.signUp({preventDefault(){}});
    expect(w.document.getElementById('suErr').textContent).toContain('ยังไม่พร้อม');
    expect(w.document.getElementById('suMsg').textContent).toBe('');dom.window.close();
  });
  it('handles expired callbacks without displaying the provider supplied markup',()=>{
    const {dom,w}=setup('https://fixture.example/#error=access_denied&error_code=otp_expired&error_description=%3Cimg%20src=x%20onerror=bad()%3E');
    expect(w.document.getElementById('siErr').textContent).toContain('หมดอายุ');
    expect(w.document.getElementById('authModalBackdrop').classList.contains('open')).toBe(true);
    expect(w.location.hash).toBe('#community');expect(w.document.querySelector('img')).toBeNull();dom.window.close();
  });
  it('shows and re-hides the password, and closing always hides it again',()=>{
    const {dom,w}=setup();const input=w.document.getElementById('siPassword'),eye=input.parentElement.querySelector('.auth-eye');
    w.CmeAuth.togglePassword('siPassword',eye);expect(input.type).toBe('text');expect(eye.getAttribute('aria-pressed')).toBe('true');
    w.CmeAuth.close();expect(input.type).toBe('password');expect(eye.getAttribute('aria-pressed')).toBe('false');dom.window.close();
  });
  it('clears all entered credentials when closing the dialog',()=>{
    const {dom,w}=setup();w.document.getElementById('siPassword').value='fixture';w.document.getElementById('siOtp').value='123456';
    w.CmeAuth.close();for(const id of ['siPassword','siOtp','suPassword'])expect(w.document.getElementById(id).value).toBe('');dom.window.close();
  });
  it('rejects incomplete codes before calling the provider and clears an expired code',async()=>{
    const {dom,w,auth}=setup();w.document.getElementById('siOtp').value='123';await w.CmeAuth.verifyCode();expect(auth.verifyOtp).not.toHaveBeenCalled();
    auth.verifyOtp.mockResolvedValueOnce({error:{code:'otp_expired'}} as any);w.document.getElementById('siOtp').value='123456';await w.CmeAuth.verifyCode();
    expect(w.document.getElementById('siOtp').value).toBe('');expect(w.document.getElementById('siErr').textContent).toContain('หมดอายุ');dom.window.close();
  });
  it('prevents overlapping submissions while the provider request is pending',async()=>{
    const {dom,w,auth}=setup();let release:any;auth.signUp.mockImplementationOnce(()=>new Promise(resolve=>release=resolve));
    const first=w.CmeAuth.signUp({preventDefault(){}});await w.CmeAuth.signUp({preventDefault(){}});
    expect(auth.signUp).toHaveBeenCalledTimes(1);expect(w.document.getElementById('suSubmitBtn').disabled).toBe(true);
    release({data:{session:null},error:null});await first;expect(w.document.getElementById('suSubmitBtn').disabled).toBe(false);dom.window.close();
  });
  it('keeps an incident destination through an emailed login callback',async()=>{
    const id='20000000-0000-4000-8000-000000000001';
    const {dom,w,auth,opened}=setup('https://fixture.example/?incident='+id);
    await w.CmeAuth.sendLink();expect(auth.signInWithOtp.mock.calls[0][0]).toMatchObject({options:{emailRedirectTo:'https://fixture.example/?incident='+id}});
    w.CmeAuth.sessionChanged({}); // Only an actual token callback triggers automatic return.
    expect(opened).not.toHaveBeenCalled();
    await w.CmeAuth.signIn({preventDefault(){}});await new Promise(resolve=>setTimeout(resolve,5));
    expect(opened).toHaveBeenCalledWith('#community/incident/'+id);dom.window.close();
  });
});
