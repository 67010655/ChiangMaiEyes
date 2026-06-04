import json
import logging
from typing import Any

import httpx

from app.config import Settings
from app.models import AdvisorMessage, DashboardResponse

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """คุณคือ "คุณเชียงใหม่" ผู้ช่วยด้านหมอกควัน ไฟป่า ฝุ่น PM2.5 และการท่องเที่ยวจังหวัดเชียงใหม่

กติกาการตอบ:
- ตอบเป็นภาษาไทยเสมอ ยกเว้นศัพท์เทคนิคที่จำเป็น เช่น PM2.5, VIIRS, GISTDA
- อิงเฉพาะข้อมูล dashboard ที่ให้มา อย่าแต่งตัวเลขหรือแหล่งข้อมูลเพิ่ม
- ตอบสั้น กระชับ เป็นมิตร และไม่ทำให้ตื่นตระหนกเกินข้อมูล
- ถ้าแนะนำสถานที่หรือกิจกรรม ให้สัมพันธ์กับ PM2.5 จุดความร้อน ลม และสภาพอากาศปัจจุบัน
- ถ้าข้อมูลไม่พอ ให้บอกตรง ๆ แล้วแนะนำวิธีดูสถานการณ์จาก dashboard
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
