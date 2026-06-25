# Community Forest Accountability Concept

สถานะ: design exploration
วันที่: 2026-06-21

แนวทางนี้เป็น concept แยกสำหรับ ChiangMaiEyes โดยยึดระบบภาพเดิมแบบ calm civic dashboard แต่ย้ายแกนหลักจากการดูฝุ่น/จุดความร้อนอย่างเดียว ไปสู่การมองว่า “ป่าชุมชนไหนอยู่ตรงไหน ใครดูแล และสัปดาห์นี้แต่ละชุมชนทำงานดูแลไฟป่าได้อย่างไร”

## Concept Assets

- Desktop concept: `docs/design-concepts/community-forest-desktop-concept.png`
- Mobile concept: `docs/design-concepts/community-forest-mobile-concept.png`

## คำสัญญาของผลิตภัณฑ์

ChiangMaiEyes ไม่ควรเป็นแค่แผนที่ PM2.5, ลม, ควัน, และจุดความร้อน แต่ควรช่วยให้คนเชียงใหม่เห็นความสัมพันธ์ระหว่างพื้นที่ป่าชุมชน ขอบเขตอำนาจ/การจัดการ และผลงานรายสัปดาห์ของแต่ละชุมชน

แกนหลัก:

- ป่าชุมชน: ชื่อป่า หมู่บ้าน ตำบล อำเภอ พื้นที่ คณะกรรมการ แผนจัดการ และแหล่งข้อมูล
- ขอบเขตอำนาจ: แยกขอบเขตป่าชุมชน เขตจัดการไฟ เขตอำเภอ และเขตหน่วยงานรัฐเมื่อมีข้อมูล
- อันดับรายสัปดาห์: เปรียบเทียบผลงานดูแลไฟป่าและกิจกรรมไฟป่าของแต่ละชุมชนในเชียงใหม่

## Desktop Screen

โครงหลัก:

- แถบซ้าย: navigation และ layer controls
- แผนที่กลาง/ขวา: แผนที่เชียงใหม่เป็นพระเอก พร้อมขอบเขตป่าชุมชน เขตจัดการไฟ จุดความร้อน และทิศทางลม
- inspector ขวา: รายละเอียดป่าชุมชนที่เลือก หน่วยงาน/ผู้ดูแล กิจกรรม แหล่งข้อมูล และลิงก์
- ตารางล่าง: อันดับรายสัปดาห์ของป่าชุมชน
- แถบแหล่งข้อมูล: อธิบาย `LIVE`, `DERIVED`, `PROTOTYPE`, `MANUAL FALLBACK`

state สำคัญ:

- เลือกป่าชุมชนแล้ว boundary ต้องเด่น
- เห็น fire-management zone ที่เกี่ยวข้อง
- hover หรือเลือก ranking row แล้ว map + inspector ต้องเปลี่ยนตาม
- prototype/derived boundary ต้องติดป้ายตรงไปตรงมา

## Mobile Screen

ลำดับ mobile:

1. Topbar และสถานะข้อมูลล่าสุด
2. เลือกสัปดาห์ + note ว่าคำนวณใหม่เมื่อไร
3. map preview พร้อม boundary chips
4. summary ป่าชุมชนที่เลือก
5. top ranking รายสัปดาห์
6. เบอร์สายด่วน/หน่วยงาน
7. bottom nav: แผนที่, อันดับ, ส่งรายงาน, แหล่งข้อมูล

หลัก mobile: map และ selected forest มาก่อน, ranking ต้องถึงเร็ว, emergency contacts อยู่ต่ำกว่าแต่ไม่หาย

## Weekly Ranking Model

ranking ต้องให้ความรู้สึกเป็น public accountability ไม่ใช่เกมหรือการแข่งขันเพื่อความสนุก

columns ที่ควรมี:

- อันดับ
- ป่าชุมชน
- อำเภอ / เขตจัดการไฟ
- คะแนนรวม
- ลาดตระเวน
- แนวกันไฟ
- จัดการเชื้อเพลิง
- แนวโน้มกิจกรรมไฟป่า
- รายงานล่าสุด
- source mode

dimension คะแนนที่ผูกกับ backend เดิมได้:

- Management
- Prevention
- Utilization
- Ecological outcome

## Copy Source Of Truth

ตัวหนังสือในภาพ imagegen เป็น visual guidance เท่านั้น ไม่ใช่ source of truth สำหรับ production copy

copy หลักที่ควรใช้:

- ป่าชุมชน
- ขอบเขตอำนาจ
- เขตจัดการไฟ
- อันดับรายสัปดาห์
- ผลงานดูแลไฟป่า
- กิจกรรมไฟป่า
- ลาดตระเวน
- แนวกันไฟ
- จัดการเชื้อเพลิง
- จุดความร้อน
- ข้อมูลต้นแบบ
- คำนวณทุกวันอาทิตย์
- รายงานภาคสนาม

## Component Inventory

components ที่ควรแยก:

- `SourceModeChip`: live / derived / prototype / manual fallback
- `LayerToggleRow`: icon, label, checked state, source mode
- `CommunityForestInspector`: identity, authority, activity, source provenance
- `WeeklyForestLeagueTable`: dense desktop ranking table
- `WeeklyForestRankList`: mobile top ranking list
- `BoundaryLegend`: community forest, fire-management zone, district, hotspot, wind
- `FieldReportCTA`: patrol, firebreak, fuel-management, photo/report action
- `EmergencyAgencyStrip`: contact rail ที่ไม่แย่ง priority หลัก

## Design Rules

- แผนที่ยังเป็น signature component
- สีแดง/ส้มใช้เฉพาะ fire หรือ risk
- สีฟ้าใช้เฉพาะ wind
- ranking ต้องไม่เหมือน gambling, trading, crypto
- ขอบเขตต้องบอก confidence: official, estimated, derived, prototype
- prototype boundary ต้องติดป้ายชัด
- Thai labels ต้องอ่านได้จริงบน mobile

## Figma Plan

frames ที่ควรสร้าง:

- `01 Desktop - Community Forest Accountability`
- `02 Mobile - Field Ranking`
- `03 Components - Governance Dashboard`
- `04 Tokens - ChiangMaiEyes Civic Green`

pass ถัดไปใน Figma:

- แปลง screenshots เป็น editable frames
- วาง copy ใหม่เป็น native text
- สร้าง variants สำหรับ layer toggles, source chips, ranking rows, inspector states
- เพิ่ม selected community forest state และ empty/no-report state

## Implementation Notes

repo hooks ที่มีอยู่แล้ว:

- `frontend/src/data/community-forests-prototype.json`
- `frontend/src/data/fire-management-zones-prototype.json`
- `frontend/src/components/DashboardMap.tsx`
- `backend/app/weekly_forest_league.py`
- `backend/tests/test_weekly_forest_league.py`

อย่าแทน production UI ทันที ทางที่ดีกว่าคือทำเป็น route แยก branch แยก หรือ feature flag ก่อน
