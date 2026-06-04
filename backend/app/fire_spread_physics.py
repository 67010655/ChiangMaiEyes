# Physics based fire spread and risk factors for Chiang Mai districts

DISTRICT_PHYSICS = {
    "แม่แจ่ม": {
        "slope_deg": 28.0,
        "elevation_m": 850,
        "forest_type": "ป่าเต็งรังและป่าสนเขา (เชื้อเพลิงใบไม้แห้งและหญ้าหนาแน่น)",
        "fuel_flammability": 1.8,  # Very High
        "history_level": "เกิดไฟป่าซ้ำซากระดับวิกฤต",
        "history_multiplier": 1.5,
    },
    "จอมทอง": {
        "slope_deg": 32.0,
        "elevation_m": 1450,
        "forest_type": "ป่าดิบเขาและป่าสนเขา (เศษใบสนแห้งสะสมปริมาณมาก)",
        "fuel_flammability": 1.5,  # High
        "history_level": "เกิดไฟป่าซ้ำซากปานกลาง-สูง",
        "history_multiplier": 1.3,
    },
    "เชียงดาว": {
        "slope_deg": 35.0,
        "elevation_m": 1100,
        "forest_type": "ป่าเบญจพรรณและป่าเต็งรังบนเขาหินปูน (พุ่มไม้แห้งและไผ่ติดไฟง่าย)",
        "fuel_flammability": 1.6,  # High
        "history_level": "เกิดไฟป่าซ้ำซากสูง",
        "history_multiplier": 1.4,
    },
    "แม่ริม": {
        "slope_deg": 18.0,
        "elevation_m": 420,
        "forest_type": "ป่าเบญจพรรณผลัดใบ (แห้งแล้งสะสมปานกลาง)",
        "fuel_flammability": 1.2,  # Moderate
        "history_level": "เกิดไฟป่าซ้ำซากต่ำ-ปานกลาง",
        "history_multiplier": 1.1,
    },
    "ฝาง": {
        "slope_deg": 26.0,
        "elevation_m": 920,
        "forest_type": "ป่าสนเขาและป่าดิบเขา (เศษใบไม้แห้งและใบสนสะสมหนาแน่น)",
        "fuel_flammability": 1.5,  # High
        "history_level": "เกิดไฟป่าซ้ำซากปานกลาง-สูง",
        "history_multiplier": 1.3,
    },
    "เมืองเชียงใหม่": {
        "slope_deg": 12.0,
        "elevation_m": 310,
        "forest_type": "ป่าเบญจพรรณสลับสวนอุทยานและแนวปะทะเขตเมือง",
        "fuel_flammability": 0.8,  # Low
        "history_level": "เกิดไฟป่าซ้ำซากต่ำ (ได้รับการเฝ้าระวังเข้มงวด)",
        "history_multiplier": 1.0,
    }
}

DEFAULT_PHYSICS = {
    "slope_deg": 20.0,
    "elevation_m": 500,
    "forest_type": "ป่าเบญจพรรณผสมพื้นที่เกษตรกรรมชายขอบป่า",
    "fuel_flammability": 1.2,  # Moderate
    "history_level": "เกิดไฟป่าซ้ำซากปานกลาง",
    "history_multiplier": 1.2,
}

def get_district_physics(district_name: str | None) -> dict:
    if not district_name:
        return DEFAULT_PHYSICS
    # Normalize name: remove "อ." or "อำเภอ" prefixes and whitespaces
    name = district_name.replace("อำเภอ", "").replace("อ.", "").strip()
    return DISTRICT_PHYSICS.get(name, DEFAULT_PHYSICS)
