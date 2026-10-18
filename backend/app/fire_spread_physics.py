# District identifiers; physical inputs require source evidence.

CHIANG_MAI_DISTRICTS = [
    "เมืองเชียงใหม่",
    "จอมทอง",
    "แม่แจ่ม",
    "เชียงดาว",
    "ดอยสะเก็ด",
    "แม่แตง",
    "แม่ริม",
    "สะเมิง",
    "ฝาง",
    "แม่อาย",
    "พร้าว",
    "สันป่าตอง",
    "สันกำแพง",
    "สันทราย",
    "หางดง",
    "ฮอด",
    "ดอยเต่า",
    "อมก๋อย",
    "สารภี",
    "เวียงแหง",
    "ไชยปราการ",
    "แม่วาง",
    "แม่ออน",
    "ดอยหล่อ",
    "กัลยาณิวัฒนา",
]

# Compatibility names retained for district enumeration. These are missing
# measurements, not fabricated district fuel/slope/history profiles.
DEFAULT_PHYSICS = {
    'slope_deg': None, 'elevation_m': None, 'fuel_flammability': None,
    'history_multiplier': None, 'forest_type': 'ยังไม่มีผลสำรวจเชื้อเพลิง',
    'history_level': 'ไม่ใช้ค่าคงที่ประวัติไฟในสูตร',
}
DISTRICT_PHYSICS = {district: DEFAULT_PHYSICS.copy() for district in CHIANG_MAI_DISTRICTS}


def get_district_physics(district_name: str | None) -> dict:
    name = (district_name or '').replace('อำเภอ','').replace('อ.','').strip()
    return DISTRICT_PHYSICS.get(name,DEFAULT_PHYSICS)
