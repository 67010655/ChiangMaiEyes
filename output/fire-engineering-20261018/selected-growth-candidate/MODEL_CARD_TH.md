# โมเดลแนวไฟทดลองที่เลือกจากข้อมูลเก่า

ยังไม่พร้อมใช้เป็นเส้นแนวไฟจริง ไม่มีการเชื่อมเข้าเว็บหรือ deploy

รุ่น `point_no_pm_large__0.03` ฝึกสุดท้ายด้วย19เหตุปี2024–2025 ใช้ภาพและสถานะก่อนเริ่มทาย,จุดVIIRSย้อนหลังที่สมมติdelay3ชั่วโมง,ภูมิประเทศ/พืชพรรณ และอากาศพยากรณ์จากIFSrunก่อนหน้า รุ่นนี้ไม่ใช้PM/Himawari/ESA/corner-gridในขั้นทำนาย ไม่ต้องเรียกแหล่งเหล่านั้นเพื่อรันตัวที่เลือก

เลือกarchitecture/thresholdด้วย2025date-blockedCV แล้วตรึงก่อนประเมิน2026ซ้ำ ปี2026ถูกใช้ในรอบก่อนแล้ว จึงไม่ใช่freshholdout ไม่มีการปรับthresholdจากคะแนน2026

เป้าหมายคือรอยspectral-changeใหม่20ม.ที่ภาพหลังตรวจได้ตามช่วงภาพจริง ไม่ใช่fire-arrivaltime12hหรือprobabilityที่calibrateแล้ว ผลปี2026ได้Dice3.05%ใน11เหตุเดิม และ4.66%ใน8เหตุเพิ่ม พื้นที่นอกapplicability20คือunknown/unmodeled ห้ามเรียกปลอดไฟ

น้ำหนัก:model.joblib | schema:feature-contract.json | hash:82450b4d2cb819bf2a11a4870f8df34163c6a684727cc7c1e9333cdc1d5b69a3

รันในworkspaceเดิมด้วยสภาพแวดล้อมวิจัยที่มีอยู่:

```powershell
backend/.venv-research/Scripts/python -X utf8 backend/scripts/finalize_refit_fire_engineering.py --replay-case 2026-02-12-T47QMV-4771-19818-bank
```

ผลอยู่refit-loop/replay/<case-id>/prediction.npz พร้อมprediction-receipt.json ชุดinputที่ให้ตัวทำนายมีเพียงcase.json,initial-state.npz,single-run-weather.json ไม่มีภาพสุดท้ายหรือtargetlabel และตรวจแล้วpixelตรงกับbenchmark

ข้อมูลภาพเริ่มต้นถูกสมมติพร้อมที่acquisitionและคลังIFSเก่าเป็นhindcast;ไม่ใช่การรับรองas-issuedoperationalaccuracy. รายละเอียดผลรวมและข้อคัดออกอยู่SUMMARY_TH.md/CONSOLIDATED_DECISION.json
