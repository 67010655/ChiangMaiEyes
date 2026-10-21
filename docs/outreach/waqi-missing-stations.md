# ข้อความถึง WAQI เรื่องสถานีในเชียงใหม่หายไป (ร่างให้คุณส่งเอง)

ส่งเมื่อ: ถ้าวันที่ 23 ต.ค. 2026 ยังได้สถานีในเชียงใหม่ไม่ถึงราว 60 จุด
ส่งทาง: แบบฟอร์มเดิมที่ https://aqicn.org/contact/ (เลือกหัวข้อ API / data)
ผมยังไม่ได้ส่งอะไร

ตัวเลขที่ใช้ในข้อความ (ตรวจจาก `/api/dust-sensors` ของเรา ซึ่งเรียก WAQI map/bounds แบบแบ่ง 6 พื้นที่ย่อย):
- 20 ต.ค. 2026 ช่วง 23:00 น. (เวลาไทย): 62 สถานีในจังหวัด
- ตั้งแต่ราว 00:00 น. วันที่ 21 ต.ค. จนถึง 21:51 น.: 8 สถานี
- ก่อนส่ง ให้ตรวจตัวเลขล่าสุดอีกครั้ง แล้วแก้บรรทัด "As of" ด้านล่าง

---

**Subject:** Map bounds API: most Chiang Mai stations missing since 21 Oct 2026

Dear World Air Quality Index Project team,

I run ChiangMaiEyes (https://chiangmaieyes.vercel.app), the non-profit site that notified you on 20 October about using your API for Chiang Mai, Thailand.

Since around 00:00 (UTC+7) on 21 October 2026, the map bounds endpoint (`/v2/map/bounds`, `networks=all`) returns only about 8 stations inside Chiang Mai province. On 20 October the same request returned about 62. We also tried splitting the province into six smaller boxes and the total stayed the same, so it does not look like a result-size limit on our side.

As of [date and time], the count is still [number].

Could you tell us whether these stations were removed or are temporarily unavailable, and whether we should query them differently? We use them only live (no archive), with attribution, as described in our earlier notice.

Thank you for your help,

Peerayoot Wattananualsakul
ChiangMaiEyes · https://chiangmaieyes.vercel.app
