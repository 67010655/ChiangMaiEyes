import json
import logging
from typing import Any

import httpx

from app.config import Settings
from app.models import AdvisorMessage, DashboardResponse
from app.evidence import pm_brief, wind_to_text

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """คุณเป็นผู้ช่วยอ่านข้อมูลของ ChiangMaiEyes สำหรับคนดูแลป่าชุมชนและประชาชนเชียงใหม่
ตอบเป็นภาษาไทยสั้นและเข้าใจง่าย โดยใช้เฉพาะข้อมูลที่ส่งมา
- แยกสิ่งที่วัด/ตรวจพบ แบบจำลอง และข้อมูลที่ยังไม่มี พร้อมเวลาและแหล่งที่มา
- AQI รวมไม่ใช่ความเข้มข้น PM2.5 ห้ามแปลงหรือเติมค่าฝุ่นที่ขาด
- ความเชื่อมั่นดาวเทียม low/nominal/high เป็นระดับคุณภาพของการตรวจพบ ไม่ใช่โอกาสเกิดไฟหรือความแม่นยำของเว็บ
- wind_direction_deg คือพัดจาก; wind_to_text คือทิศพัดไป ให้พูดชัดและระบุระดับ/ตำแหน่งอ้างอิงเมื่อมี
- จุดดาวเทียมยังไม่ยืนยันว่าไฟกำลังไหม้ และการไม่พบจุดยังไม่ยืนยันว่าไม่มีไฟ
- คะแนนและภาพการลามในระบบยังเป็นสูตรทดลอง ห้ามรับรองความปลอดภัย เวลาที่ไฟจะถึง หรือสั่งระดมกำลังจากคะแนน
- EVI/NDVI เป็นดัชนีพืชพรรณ ห้ามอ้างเป็นมวลหรือความชื้นเชื้อเพลิงที่วัดจริง
- ช่วยระบุข้อมูลที่ควรตรวจและผู้รับผิดชอบที่ต้องประสาน ไม่สมมติรายชื่อ อำนาจสั่งการ หรือเหตุภาคสนาม
- คำแนะนำเกี่ยวกับสุขภาพหรือการเข้าพื้นที่ต้องไม่เกินข้อมูล ห้ามบอกว่าปลอดภัยจาก RH หรือค่าลมอย่างเดียว
"""


class AdvisorUnavailable(RuntimeError):
    pass


def fallback_daily_briefing(dashboard: DashboardResponse) -> str:
    hotspot_quality = dashboard.data_quality.get("hotspots")
    freshness = ""
    if hotspot_quality and hotspot_quality.age_minutes is not None:
        freshness = f" ข้อมูลจุดความร้อนตรวจล่าสุดประมาณ {hotspot_quality.age_minutes} นาทีที่แล้ว"
    return (
        f"{pm_brief(dashboard.pm25)} พบจุดความร้อน {dashboard.hotspots.count} จุด "
        f"ลมพัดจาก{dashboard.weather.wind_direction_text}ไป{wind_to_text(dashboard.weather.wind_direction_deg)} ความเร็ว {dashboard.weather.wind_speed_kmh:.0f} กม./ชม. "
        f"การประเมินรวม {str(dashboard.risk.score)+'/10' if dashboard.risk.score is not None else 'ยังประเมินไม่ได้: ขาดหลักฐานเชื้อเพลิงและผลตรวจแบบจำลอง'}.{freshness} "
        "คำตอบนี้มาจากระบบประเมินพื้นฐาน ไม่ใช่โมเดล AI สด"
    )


def fallback_chat_reply(dashboard: DashboardResponse, user_message: str) -> str:
    lowered = user_message.lower()
    if any(word in lowered for word in ["pm", "ฝุ่น", "อากาศ", "air"]):
        focus = (
            f"{pm_brief(dashboard.pm25)} จาก {dashboard.pm25.source}"
        )
    elif any(word in lowered for word in ["ไฟ", "hotspot", "จุด"]):
        focus = (
            f"พบจุดความร้อน {dashboard.hotspots.count} จุด "
            f"แหล่งข้อมูล {dashboard.hotspots.source}"
        )
    elif any(word in lowered for word in ["ลม", "wind", "ควัน"]):
        focus = (
            f"ลม {dashboard.weather.wind_speed_kmh:.0f} km/h "
            f"พัดจาก{dashboard.weather.wind_direction_text}ไป{wind_to_text(dashboard.weather.wind_direction_deg)} จาก {dashboard.weather.source}"
        )
    else:
        focus = (
            f"ภาพรวมตอนนี้ {pm_brief(dashboard.pm25)}, "
            f"จุดความร้อน {dashboard.hotspots.count} จุด, "
            f"การประเมินรวม {str(dashboard.risk.score)+'/10' if dashboard.risk.score is not None else 'ยังประเมินไม่ได้'}"
        )
    return (
        f"{focus}. ตอนนี้โมเดล AI สดไม่พร้อมใช้งาน จึงตอบจากกฎพื้นฐานและข้อมูลบน dashboard เท่านั้น "
        "ใช้เป็นคำแนะนำเบื้องต้น และตรวจเวลาข้อมูลล่าสุดก่อนตัดสินใจภาคสนาม"
    )


def _dashboard_context(dashboard: DashboardResponse) -> str:
    # Get top 10 highest confidence hotspots
    hotspots = [
        {
            "district": item.district,
            "subdistrict": item.subdistrict,
            "confidence_level": item.confidence_level,
            "confidence_raw": item.confidence_raw,
            "confidence_scheme": item.confidence_scheme,
            "source": item.source,
            "landuse": item.landuse_name or item.landuse_type,
            "latitude": item.latitude,
            "longitude": item.longitude,
        }
        for item in sorted(dashboard.hotspots.items, key=lambda x: x.confidence, reverse=True)[:10]
    ]
    
    # Filter PM2.5 data: only keep top 5 stations with highest PM2.5, exclude coordinates/IDs
    pm25_data = {
        "current_pm25": dashboard.pm25.current_pm25,
        "category": dashboard.pm25.category,
        "color": dashboard.pm25.color,
        "trend": dashboard.pm25.trend,
        "latest_update": dashboard.pm25.latest_update,
        "source": dashboard.pm25.source,
        "measurement_kind": dashboard.pm25.measurement_kind,
        "note": dashboard.pm25.note,
        "stations_sample": [
            {
                "name": s.name,
                "district": s.district,
                "pm25": s.pm25,
                "trend": s.trend
            }
            for s in sorted(dashboard.pm25.stations, key=lambda x: x.pm25, reverse=True)[:5]
        ]
    }

    # Filter weather data to essential fields
    weather_data = {
        "wind_speed_kmh": dashboard.weather.wind_speed_kmh,
        "wind_direction_deg": dashboard.weather.wind_direction_deg,
        "wind_direction_text": dashboard.weather.wind_direction_text,
        "wind_to_text": wind_to_text(dashboard.weather.wind_direction_deg),
        "temperature_c": dashboard.weather.temperature_c,
        "humidity_percent": dashboard.weather.humidity_percent,
        "latest_update": dashboard.weather.latest_update,
        "source": dashboard.weather.source,
    }

    payload: dict[str, Any] = {
        "pm25": pm25_data,
        "weather": weather_data,
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
                last_error = f"Groq key rejected with {response.status_code}: {response.text}"
                continue
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if text:
                return text.strip()
            last_error = "Groq returned an empty response"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("Groq advisor request failed")

    raise AdvisorUnavailable(last_error)


def generate_daily_briefing(settings: Settings, dashboard: DashboardResponse) -> str:
    context = _dashboard_context(dashboard)
    prompt = (
        "สรุปสถานการณ์วันนี้ให้ประชาชนฟังไม่เกิน 150 คำ โดยครอบคลุม PM2.5, จุดความร้อน, ลม, "
        "คำแนะนำสุขภาพ และกิจกรรมหรือพื้นที่ที่เหมาะสมกับสภาพอากาศปัจจุบัน\n\n"
        f"[dashboard]\n{context}"
    )
    try:
        return _call_groq(
            settings,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
        )
    except AdvisorUnavailable as groq_exc:
        if settings.gemini_api_key:
            logger.info("Groq unavailable (rate-limited/misconfigured) - falling back to Gemini for briefing")
            try:
                import google.generativeai as genai  # type: ignore[import-not-found]
                genai.configure(api_key=settings.gemini_api_key)
                model = genai.GenerativeModel(settings.gemini_model, system_instruction=SYSTEM_PROMPT)
                config = genai.types.GenerationConfig(max_output_tokens=800, temperature=0.75)
                response = model.generate_content(prompt, generation_config=config)
                return response.text.strip()
            except Exception as gemini_exc:
                logger.error("Gemini fallback failed")
                raise AdvisorUnavailable(f"Both Groq and Gemini failed. Groq error: {groq_exc}. Gemini error: {gemini_exc}") from gemini_exc
        else:
            raise


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

    try:
        return _call_groq(settings, messages, max_tokens=600)
    except AdvisorUnavailable as groq_exc:
        if settings.gemini_api_key:
            logger.info("Groq unavailable (rate-limited/misconfigured) - falling back to Gemini for chat")
            try:
                import google.generativeai as genai  # type: ignore[import-not-found]
                genai.configure(api_key=settings.gemini_api_key)
                system_inst = f"{SYSTEM_PROMPT}\n\n[dashboard]\n{context}"
                model = genai.GenerativeModel(settings.gemini_model, system_instruction=system_inst)
                
                gemini_history = []
                for msg in history[-12:]:
                    gemini_history.append({
                        "role": "user" if msg.role != "model" else "model",
                        "parts": [msg.text]
                    })
                
                config = genai.types.GenerationConfig(max_output_tokens=600, temperature=0.75)
                chat = model.start_chat(history=gemini_history)
                response = chat.send_message(user_message, generation_config=config)
                return response.text.strip()
            except Exception as gemini_exc:
                logger.error("Gemini chat fallback failed")
                raise AdvisorUnavailable(f"Both Groq and Gemini failed. Groq error: {groq_exc}. Gemini error: {gemini_exc}") from gemini_exc
        else:
            raise
