# โดเมนผู้ส่ง ChiangMaiEyes

ตรวจ 13 ตุลาคม 2026 · ไม่ได้ซื้อโดเมน เปลี่ยน DNS หรือส่งอีเมลในรอบนี้

ผู้ใช้ยืนยันให้คงการแจ้งเตือนสำหรับตัวแทนที่ได้รับอนุมัติ/เข้าสู่ระบบตามแนวทางเดิม ไม่เพิ่มการสมัครแจ้งเตือนสาธารณะในงานนี้ โค้ดส่งอีเมลปัจจุบันยังตรวจยืนยันอีเมล การอนุมัติพื้นที่ และการเลือกเปิดรับแจ้งเตือนก่อนส่ง

ชื่อผู้ส่งที่เสนอ: **ChiangMaiEyes Alerts**

ที่อยู่ผู้ส่งที่เสนอ: **alerts@chiangmaieyes.com** เมื่อเป็นเจ้าของโดเมนและยืนยันกับ Resend แล้ว `Alerts@ChiangMaiEyes` ยังขาดส่วนท้ายโดเมนสำหรับใช้อีเมลทางอินเทอร์เน็ต

ผลจาก Vercel Registrar API ขณะตรวจ:

| ชื่อ | สถานะที่ API คืน | จด 1 ปี (USD) | ต่ออายุ 1 ปี (USD) |
|---|---|---:|---:|
| chiangmaieyes.com | available=true, ไม่ใช่ premium | 11.25 | 11.25 |
| chiangmaieyes.org | available=true, ไม่ใช่ premium | 9.99 | 10.99 |

ราคาและชื่อว่างเป็นผล ณ เวลาตรวจ ยังไม่ได้จองไว้ อ้างอิงการตรวจแบบ exact names ด้วย [Vercel Registrar API](https://vercel.com/docs/domains/registrar-api)

ขั้นตอน: จดโดเมนที่เลือก → เพิ่มโดเมนใน Resend → ใส่ DNS ตามค่าที่ Resend ให้ → รอ verified → ตั้งผู้ส่งในระบบ และ custom SMTP สำหรับอีเมลยืนยันสมาชิก ผู้รับใช้ Gmail เดิมได้ และเว็บไซต์ยังใช้ chiangmaieyes.vercel.app ต่อได้ ไม่ต้องย้ายเว็บไซต์เพื่อใช้อีเมลผู้ส่ง [Resend verified domains](https://resend.com/docs/dashboard/domains/introduction) · [Supabase SMTP](https://supabase.com/docs/guides/auth/auth-smtp)

ตรวจบัญชี Resend ที่เชื่อมอยู่ด้วย API แบบอ่านอย่างเดียว ได้ HTTP 200 และรายการ domains ว่าง; config ปัจจุบันเป็น `onboarding@resend.dev` และการส่งทั่วไปปิดอยู่ โดเมนนี้ส่งทดสอบได้เฉพาะอีเมลที่ผูกกับบัญชี Resend [ข้อจำกัด resend.dev](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain)
