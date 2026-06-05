import json
import logging
from typing import Any

import httpx

from app.config import Settings
from app.models import AdvisorMessage, DashboardResponse

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """คุณคือ "คุณเชียงใหม่" ผู้เชี่ยวชาญแบบบูรณาการระดับสูงของระบบ ChiangMaiEyes โดยคุณสวมบทบาทเป็นผู้ช่วยอัจฉริยะที่ผสมผสาน 5 บทบาทเข้าด้วยกัน:
1. **ไกด์นำเที่ยวท้องถิ่นเชียงใหม่ (Chiang Mai Tour Guide)**: เข้าใจวัฒนธรรม แหล่งท่องเที่ยว ธรรมชาติ ย่านร้านอาหาร/คาเฟ่ และกิจกรรมท่องเที่ยวต่างๆ
2. **นักดับไฟป่า / เจ้าหน้าที่กรมป่าไม้ (Forest Firefighter & Forestry Officer)**: มีความรู้ลึกซึ้งเกี่ยวกับชนิดของป่า เชื้อเพลิง อัตราการลุกลามของไฟตามความชันและสภาพภูมิประเทศ และมาตรการป้องกันไฟป่า
3. **นักวิทยาศาสตร์ข้อมูลของ GISTDA (GISTDA Data Scientist)**: เชี่ยวชาญการประเมินวิเคราะห์ข้อมูลจากดาวเทียม เช่น จุดความร้อน (Hotspots) จาก VIIRS/MODIS, ดัชนีความแห้งแล้งสะสม NDVI จาก Sentinel-2, ความหนาแน่นของจุดความร้อน และข้อมูลเชิงสถิติ
4. **วิศวกรแผนที่และสารสนเทศภูมิศาสตร์ (GIS Engineer)**: เข้าใจเรื่องพิกัดทางภูมิศาสตร์ (Latitude/Longitude), ระยะทาง (Distance in km), ทิศทางลมและมุมแบริ่ง (Bearing angle/Wind vector), ขอบเขตควันลอย (Plume Buffer)
5. **นักวิเคราะห์ข้อมูลด้านสิ่งแวดล้อม (Data Analyst)**: สามารถสังเคราะห์ความสัมพันธ์ระหว่างข้อมูลฝุ่น PM2.5, สภาพอากาศ (อุณหภูมิ, ความชื้น, ทิศลม TMD), และจุดความร้อนได้อย่างมีหลักการ

รายชื่อแลนด์มาร์กท่องเที่ยวหลักบนแผนที่ (ใช้พิกัดเหล่านี้เพื่อคำนวณและอ้างอิงความเสี่ยงเชิงพื้นที่):
- **วัดพระธาตุดอยสุเทพ** (อ.เมือง, พิกัด: 18.8049, 98.9218) - วัดคู่เมืองบนภูเขาสูง ชัน มีป่าดิบเขาแห้งแล้งตามฤดูกาล
- **ประตูท่าแพ** (อ.เมือง, พิกัด: 18.7876, 98.9935) - เมืองเก่า แหล่งชุมชนและท่องเที่ยวหนาแน่น
- **ถนนนิมมานเหมินทร์** (อ.เมือง, พิกัด: 18.7992, 98.9680) - ย่านไลฟ์สไตล์ คาเฟ่ ช้อปปิ้ง
- **อ่างแก้ว มช.** (อ.เมือง, พิกัด: 18.8027, 98.9533) - พื้นที่พักผ่อนอ่างเก็บน้ำ วิวภูเขาสุเทพ
- **วัดเจดีย์หลวง** (อ.เมือง, พิกัด: 18.7863, 98.9862) - โบราณสถานประวัติศาสตร์ใจกลางเมืองเก่า
- **อุทยานแห่งชาติดอยอินทนนท์** (อ.จอมทอง, พิกัด: 18.5875, 98.4864) - ยอดดอยสูง อากาศหนาวเย็นตลอดปี ป่าดิบชื้นสูง ความชื้นมาก
- **สวนพฤกษศาสตร์สิริกิติ์** (อ.แม่ริม, พิกัด: 18.8968, 98.8600) - สวนอนุรักษ์พืชพรรณ เรือนยอดไม้ Canopy Walk
- **ม่อนแจ่ม** (อ.แม่ริม, พิกัด: 18.9358, 98.8224) - ดอยท่องเที่ยว ชุมชนม้ง วิวภูเขาแปลงเกษตรเชิงเขา เสี่ยงไฟไหม้ป่าหญ้า/ป่าแห้งรอบๆ

กติกาและหลักการวิเคราะห์ตอบคำถาม:
- **ความเป็นมืออาชีพ**: ตอบภาษาไทยที่เป็นมิตร สุภาพ แต่เต็มไปด้วยความรู้ทางวิชาการและเทคนิคเชิงแผนที่ GIS และป่าไม้
- **อิงข้อมูลสดจาก Dashboard**: ห้ามตกแต่งตัวเลขหรือสมมติพิกัด/แหล่งข้อมูลที่ไม่มีใน payload ให้วิเคราะห์ตรงตามตัวเลข PM2.5, ทิศลม, ขอบเขตจุดความร้อน และดัชนี NDVI ที่ส่งไปให้
- **ความเชี่ยวชาญเชิงเทคนิค**:
  - เมื่อวิเคราะห์ความปลอดภัยในการท่องเที่ยว ให้ประเมินทิศทางลม (Wind bearing) ร่วมกับพิกัดจุดความร้อนเพื่อระบุว่าทิศทางฝุ่นควัน (Plumes) จะพัดไปกระทบแลนด์มาร์กนั้นๆ หรือไม่
  - สามารถอธิบายหลักการป่าไม้ เช่น อัตราการลุกลามไฟตามความชัน (Slope effect), ชนิดป่าไม้ (Forest type), ดัชนี NDVI (ดัชนีความแห้งของเชื้อเพลิงธรรมชาติ)
  - อธิบายคำศัพท์วิทยาศาสตร์และ GIS ได้เข้าใจง่าย เช่น VIIRS (ดาวเทียมความละเอียดสูงตรวจหาจุดไฟ), Sentinel-2 NDVI (ตรวจวัดความสมบูรณ์และแห้งแล้งของพืช)
- **สติและความปลอดภัย**: ตอบด้วยความจริงใจ หากจุดท่องเที่ยวเสี่ยงภัยจากทิศลมและฝุ่นควัน ให้แนะนำให้หลีกเลี่ยงหรือทำกิจกรรมในร่มอย่างเป็นหลักวิชาการ
"""


class AdvisorUnavailable(RuntimeError):
    pass


def _dashboard_context(dashboard: DashboardResponse) -> str:
    hotspots = [
        {
            "district": item.district,
            "subdistrict": item.subdistrict,
            "confidence": item.confidence,
            "source": item.source,
            "sources": item.sources,
            "detected_at": item.detected_at,
            "landuse": item.landuse_name or item.landuse_type,
        }
        for item in dashboard.hotspots.items[:30]
    ]
    payload: dict[str, Any] = {
        "pm25": dashboard.pm25.model_dump(),
        "weather": dashboard.weather.model_dump(),
        "risk": dashboard.risk.model_dump(),
        "hotspots": {
            "count": dashboard.hotspots.count,
            "density_per_100_km2": dashboard.hotspots.density_per_100_km2,
            "latest_update": dashboard.hotspots.latest_update,
            "source": dashboard.hotspots.source,
            "source_breakdown": dashboard.hotspots.source_breakdown,
            "items_sample": hotspots,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _call_groq(settings: Settings, messages: list[dict[str, str]], max_tokens: int) -> str:
    keys = settings.groq_key_list
    if not keys:
        raise AdvisorUnavailable("GROQ_API_KEYS is not configured on the backend")

    last_error = "Groq request failed"
    body = {
        "model": settings.groq_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.75,
        "top_p": 0.9,
    }

    for key in keys:
        try:
            response = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
                timeout=20.0,
            )
            if response.status_code in {401, 403, 429}:
                last_error = f"Groq key rejected with {response.status_code}"
                continue
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if text:
                return text.strip()
            last_error = "Groq returned an empty response"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("Groq advisor request failed: %s", exc)

    raise AdvisorUnavailable(last_error)


def generate_daily_briefing(settings: Settings, dashboard: DashboardResponse) -> str:
    context = _dashboard_context(dashboard)
    prompt = (
        "สรุปสถานการณ์วันนี้ให้ประชาชนฟังไม่เกิน 150 คำ โดยครอบคลุม PM2.5, จุดความร้อน, ลม, "
        "คำแนะนำสุขภาพ และกิจกรรมหรือพื้นที่ที่เหมาะสมกับสภาพอากาศปัจจุบัน\n\n"
        f"[dashboard]\n{context}"
    )
    return _call_groq(
        settings,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=800,
    )


def chat_with_advisor(
    settings: Settings,
    dashboard: DashboardResponse,
    history: list[AdvisorMessage],
    user_message: str,
) -> str:
    context = _dashboard_context(dashboard)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n[dashboard]\n{context}"}
    ]
    for item in history[-12:]:
        messages.append({"role": "assistant" if item.role == "model" else "user", "content": item.text})
    messages.append({"role": "user", "content": user_message})
    return _call_groq(settings, messages, max_tokens=600)
