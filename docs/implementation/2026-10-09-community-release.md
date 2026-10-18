# ชุด 2: พื้นที่ป่าชุมชนและประสานเหตุ

ตรวจและปล่อย 9 ตุลาคม 2026 (ICT)

## สถานะ

ขึ้น production สำหรับทดลองระบบแล้ว: https://chiangmaieyes.vercel.app/

- Frontend: `dpl_AdaUrLDGQhNM66rFzfCZD5pCvA2q`
- Backend: `dpl_BdM236jQyMAH5RSUHfv7DANMR2E8`
- บัญชีเดิมที่ผู้ใช้กำหนดเข้าสู่ระบบเป็นผู้ดูแลได้ด้วยรหัสครั้งเดียว โดยไม่เปลี่ยนรหัสผ่าน
- ขอบเขตและรหัสป่าอ้างอิง 677 ระเบียนจากไฟล์ที่ได้รับผ่าน RECOFTC ชื่อที่ซ้ำกันแสดงตำบลและรหัสข้อมูลเพื่อแยกขอบเขต
- ยังไม่มีตัวแทนชุมชนที่ผ่านการตรวจสอบในระบบ และไม่มี incident ภาคสนามใหม่ ไม่สร้างเหตุหรือตัวแทนสมมติลง production

## งานที่เพิ่ม

1. สมาชิกต้องได้รับอนุมัติจากผู้ดูแลก่อนใช้งานพื้นที่ ข้อมูล role และผลยืนยันตั้งเองไม่ได้
2. “ป่าของฉัน”: แผนที่ polygon จริง จุดความร้อนและสถานีฝุ่นภายในขอบเขต ลมระบุว่าเป็นข้อมูลอ้างอิงจังหวัด พร้อมเวลาและที่มา ไม่มีสถานีฝุ่นในป่าจะไม่ใช้ค่าเฉลี่ยจังหวัดแทน
3. แบบแจ้งควัน/เปลวไฟ เก็บร่างแยกตามบัญชี เวลาประเทศไทย และ UUID เดิมสำหรับ retry หลังการเชื่อมต่อขาด ไม่แสดงว่าส่งแล้วก่อน server ตอบรับ
4. Timeline และสถานะเหตุพร้อมผู้เปลี่ยน เหตุผล และ version ป้องกันเขียนทับข้อมูลที่เปลี่ยนแล้ว ผู้รับประสานและคำขอร่วมช่วยมาจากคนที่มีสิทธิ์
5. เชื่อมรายงานรอตรวจสอบที่เป็นเหตุเดียวกันเข้ากับเหตุหลักโดยผู้รับผิดชอบ พร้อมรักษาประวัติและรูปต้นทาง ไม่รวมจากระยะใกล้กันโดยอัตโนมัติ
6. แนบรูปส่วนตัว JPEG/PNG/WebP ไม่เกิน 4 MB และ 12 ล้านพิกเซล สูงสุด 10 รูปต่อเหตุ ตรวจและแปลงเป็น JPEG ลบ EXIF เก็บใน private bucket และตรวจสิทธิ์ใหม่ทุกครั้งที่อ่านรูป
7. เหตุและพิกัดละเอียดอยู่ในพื้นที่ที่มีสิทธิ์ Public view แสดงเฉพาะชื่อป่า สถานะ และเวลาที่ผู้รับผิดชอบเลือกเผยแพร่
8. โหลดเหตุและประวัติเก่าเพิ่มเติมได้ ครั้งละ 200 รายการ การเก็บประวัติไม่ได้ตัดตาม 3 วันของหมุดรายงานเดิม
9. เลือกรับอีเมลเหตุใหม่/สรุปรายวันและเวลาพักได้ ค่าเริ่มต้นไม่เปิดรับ Worker ตรวจสิทธิ์สมาชิกและการยินยอมอีกครั้งก่อนส่ง ใช้ outbox/dedup/lease และ Resend idempotency key ไม่ retry ข้อผิดพลาดผู้ส่ง 4xx ที่ต้องแก้ค่า
10. แสดงคิวและผลนำส่งให้ผู้ดูแล พร้อมปุ่มอัปเดต รับ callback ที่ตรวจ signature และ replay จาก Resend; bounce/complaint ปิดการยินยอมรับต่อ
11. ปิดหน้าป่าชุมชนเมื่อสลับหน้า/ส่งออก ล้าง DOM และ blob รูปเมื่อปิดหรือออกจากระบบ ป้องกันติดหน้าส่วนตัวใน PDF คืนตำแหน่งเลื่อนด้านบนเมื่อเปลี่ยนหน้า

## ฐานข้อมูลและข้อมูลเดิม

สำรอง 4 ตารางเดิมและ grants/policies ก่อนเปลี่ยน เก็บใน `.local/backups/20261009-before-community/` ซึ่งไม่อยู่ใน Git หรือ deployment

ใช้ migrations:

- `20261009190000_community_coordination.sql`
- `20261009193000_community_mail_queue.sql`
- `20261009195000_evidence_and_mail_claim.sql`
- `20261009194000_workflow_fixes.sql` (ใช้หลัง evidence สำหรับอัปเดตระบบที่ลง core ไปแล้ว)
- `20261009200000_private_legacy_reports.sql` (ใช้หลัง frontend/API ใหม่ขึ้นแล้ว)

รายงานเดิม `manual_hotspot_reports` ทั้ง 6 รายการยังอยู่ครบ ยกเลิกผ่าน API เป็น soft cancellation ไม่ลบแถว อ่านได้เฉพาะเจ้าของผ่าน API ใหม่ การอ่านตารางเดิมแบบ anonymous ตรวจได้ HTTP 401

## ผลตรวจ

| การตรวจ | ผลและขอบเขต |
|---|---|
| Backend pytest | 113 ผ่าน จาก cwd `backend` |
| Frontend Vitest | 67 ผ่าน รวม 14 กรณี SQL บน PostgreSQL ผ่าน PGlite และ 7 กรณี workspace บน JSDOM |
| สิทธิ์หลายผู้ใช้ | Fixtures ตรวจ self-approval/direct privileged insert, ข้อมูลคนละป่า, คำเชิญก่อน/หลังรับ, revocation, private photos, เปลี่ยนสถานะ/version และเผยแพร่เฉพาะ coarse summary |
| อีเมล | ตรวจ opt-in/quiet hours/dedup/retry/4xx/signature/replay/bounce; ส่งผ่าน UI ไปผู้รับมหาวิทยาลัยที่ผู้ใช้อนุมัติ Resend รายงาน `delivered` และ callback บันทึก `delivered` ใน DB แล้ว ไม่ถือเป็นหลักฐานว่าคนเปิดอ่านหรืออยู่ใน Inbox แทน Spam |
| Cloud API | บัญชีผู้ดูแลจริงอ่าน `/me`, incidents, review queue, mail status ได้ HTTP 200; ไม่มี JWT ได้ 401 |
| Read load | 12 requests, concurrency 4, HTTP 200 ทั้งหมด, median 1,791 ms, p95 5,418 ms ตัวอย่างเล็ก ไม่ใช่ capacity test สำหรับใช้งานทั้งจังหวัด ดู JSON ที่แนบ |
| Rendered UI | HTTPS production: 1280×800 และ 390×844, dark/light ไม่มี horizontal overflow; reduced motion ให้ transition 0s; เปิดได้ครั้งละหนึ่ง overlay และคีย์บอร์ดใช้ปุ่มแบบฟอร์มได้ |
| PDF | สร้างจาก print engine ของ browser แล้วเปิด/แยกข้อความ/เรนเดอร์ดูทั้ง 2 หน้า ภาษาไทยและแผนที่อ่านได้ ไม่ติด workspace ส่วนตัว ขอบเขตคือ print rendering ไม่ใช่การทดลองบันทึกผ่าน native print dialog ของผู้ใช้ |
| Build/audit | Cloud build ผ่าน; npm audit 0 vulnerabilities มีคำเตือนขนาด lazy 3D bundle เดิมประมาณ 1.06 MB |

Protected preview เปิดหน้าได้ แต่ request API ถูกส่งไป Vercel SSO จึงใช้การตรวจ API และ rendered UI บนโดเมนหลักหลัง promote แทน ไม่ปิด Deployment Protection

ภาพหน้าจออยู่ในโฟลเดอร์ visualizations ของ task: desktop dark, desktop light, mobile dark และ mobile light วันที่ 20261009

ตัวอย่าง PDF: `output/pdf/chiangmaieyes-forest-report-20261009.pdf`

## สิ่งที่ยังไม่เปิดหรือยังไม่ตรวจรับ

- Resend ยังไม่มีโดเมนผู้ส่งที่ยืนยัน จึงตั้ง `COMMUNITY_EMAIL_ENABLED=false` และส่งได้เฉพาะผู้รับทดสอบที่กำหนดไว้ฝั่ง server ไม่เปิดส่งถึงชาวบ้านทั่วไป
- ยังไม่ได้ทดสอบการสมัครบัญชี/รับลิงก์เข้าสู่ระบบกับอีเมลตัวแทนทั่วไปครบวงจร ต้องตรวจ Auth SMTP และ redirect configuration พร้อมโดเมนที่เจ้าของควบคุม
- ยังไม่มีผู้ทดลองจากชุมชนที่ยืนยันจริง จึงยังไม่วัดเวลาแจ้งเหตุ/หาเจ้าของเรื่องหรือรับรองผลจากภาคสนาม การทดสอบ SQL/Auth fixtures ไม่ใช่ pilot กับชาวบ้าน
- รูปแนบผ่านการตรวจ codec/metadata/สิทธิ์ด้วย tests และ private bucket ตั้งค่าจริงแล้ว แต่ยังไม่ได้อัปโหลดรูปภาคสนามของเหตุจริงผ่าน browser
- Worker ทำงานเมื่อมีการเรียก dashboard หรือผู้ดูแลสั่งตรวจ มี dedup รอบ 5 นาที แต่ไม่มีการรับรองว่าจะทำงานทุก 5 นาทีเมื่อไม่มี traffic ต้องกำหนดรอบงานและงบก่อนเปิดอีเมลจริง
- ยังไม่มีหัวหน้าป่า/ผู้สั่งการรายพื้นที่ที่ผ่านการตรวจสอบ ข้อมูลโทรศัพท์กรมป่าไม้ใช้เป็นช่องทางสอบถาม ไม่ใช้รับรองความรับผิดชอบจาก polygon

## การย้อนกลับ

แก้ไปข้างหน้าเป็นทางหลัก เพราะ migrations เพิ่มข้อมูลและ workflow ต่อเนื่อง หากต้องหยุดอีเมลให้คง `COMMUNITY_EMAIL_ENABLED=false` และปิดผู้รับทดสอบฝั่ง server แล้ว redeploy backend เก็บ outbox และ incident history ไว้

สามารถ promote deployment ก่อนหน้าที่รองรับ community API ได้โดยไม่ลบข้อมูล หากจะย้อน frontend ไปก่อนมี workspace ต้องพิจารณา legacy API/หน้าประวัติร่วมด้วย ไม่คืน anonymous grants โดยอัตโนมัติ และไม่ drop ตาราง incident/สมาชิก/รูป ใช้ backup สำหรับเทียบหรือกู้ข้อมูลเป็นรายกรณี

## แหล่งอ้างอิงของข้อกำหนด

- [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase generateLink](https://supabase.com/docs/reference/javascript/auth-admin-generatelink) และ [verifyOtp](https://supabase.com/docs/reference/javascript/auth-verifyotp)
- [Resend domains](https://resend.com/docs/dashboard/domains/introduction)
- [Resend idempotency: 24 ชั่วโมง](https://resend.com/docs/dashboard/emails/idempotency-keys)
- [Resend webhook verification](https://resend.com/docs/webhooks/verify-webhooks-requests) และ [Svix signature](https://docs.svix.com/receiving/verifying-payloads/how-manual)
- [Vercel payload limit 4.5 MB](https://vercel.com/docs/functions/limitations) ใช้เพดานรูป 4 MB ใน API
- [บัญชีโทรศัพท์กรมป่าไม้](https://forestinfo.forest.go.th/telephone_region.aspx) ตรวจในชุดแรก 9 ตุลาคม 2026

แผนที่ยังต้องติดตาม: [แผนชุด 2](./2026-10-09-next-release-plan.md), [รายการ feedback เดิม](./2026-10-09-community-feedback.md)
