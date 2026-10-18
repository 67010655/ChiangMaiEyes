# Engineering รอบ2: เพิ่มข้อมูลฝึกเก่าแบบเว้นวันและเหตุ

เลือก `point_no_pm_large__0.03` จาก2025date-CV pooledDice 8.231% เทียบparent 7.363%. Finalfitใช้19เหตุเก่า. 2026เป็นreusedretrospectiveหลังออกแบบรอบ1 ไม่ใช่unseenholdout. No2026labelsเลือกhyperparameters/threshold.

## เทียบรอบ1–2บนคำตอบชุดเดียวกัน

| ชุด | รอบ1 Dice | รอบ2 Dice | รอบ2พื้นที่ทำนายกม² | referenceกม² | intersectionกม² |
|---|---:|---:|---:|---:|---:|
| regression2026 | 3.151% | 3.049% | 11.8324 | 4.4100 | 0.2476 |
| test2026_new_cases | 4.155% | 4.663% | 7.6348 | 10.9468 | 0.4332 |

ข้อแยกสำคัญ: CVcandidateได้เรียนจากวันอื่นในปี2025 ส่วนparentเรียน2024เท่านั้น จึงเป็นการทดลองเพิ่มtrainingdata ไม่ใช่yearholdoutที่มีbudgetข้อมูลฝึกเท่ากัน คะแนนCVก่อนfinalrefitไม่ใช่คะแนนตรวจของน้ำหนักที่fitทุก19เหตุแล้ว แยกtest2026ไว้และไม่สลับthresholdตามผลนั้น

Verificationผ่าน: frozenweights/sourcearraycontent, ข้อมูลดิบ2700ไฟล์ยังเดิม, heldcase/date disjoint, ไม่มีcrossdateoverlappinglabelwindows, replay2เหตุไม่มีfutureimage/labelsและpixelตรงกัน, production6ไฟล์/old97sourcesยังเดิม ไม่มีdeploy

## รันซ้ำ

```powershell
backend/.venv-research/Scripts/python -X utf8 backend/scripts/refit_fire_engineering.py --phase selection
backend/.venv-research/Scripts/python -X utf8 backend/scripts/refit_fire_engineering.py --phase test
backend/.venv-research/Scripts/python -X utf8 backend/scripts/finalize_refit_fire_engineering.py
```
