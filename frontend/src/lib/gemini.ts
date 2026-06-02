import type { DashboardResponse } from './types';

// ─── Provider config ────────────────────────────────────────────────────────
// Priority: Groq → Gemini (whichever key is set)
// Groq:   Get free key at https://console.groq.com  (14,400 req/day, no billing)
// Gemini: Get free key at https://aistudio.google.com/apikey

const GROQ_KEY = import.meta.env.VITE_GROQ_API_KEY ?? '';
const GEMINI_KEY = import.meta.env.VITE_GEMINI_API_KEY ?? '';

// Groq key starts with 'gsk_'
const GROQ_VALID = GROQ_KEY.startsWith('gsk_') && GROQ_KEY.length >= 20;
// Gemini key: old 'AIzaSy' or new 'AQ.' format
const GEMINI_VALID =
  (GEMINI_KEY.startsWith('AIzaSy') || GEMINI_KEY.startsWith('AQ.')) &&
  GEMINI_KEY.length >= 20;

export const GEMINI_KEY_VALID = GROQ_VALID || GEMINI_VALID;

// Which provider we'll actually use
const PROVIDER: 'groq' | 'gemini' | 'none' = GROQ_VALID ? 'groq' : GEMINI_VALID ? 'gemini' : 'none';

// ─── Endpoints ──────────────────────────────────────────────────────────────
const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';
const GROQ_MODEL = 'llama-3.3-70b-versatile';

const GEMINI_MODEL = 'gemini-2.0-flash-lite';
const GEMINI_URL = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_KEY}`;

// ─── System prompt ──────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `คุณคือ "คุณเชียงใหม่" — ผู้เชี่ยวชาญด้านหมอกควันและไฟป่าประจำจังหวัดเชียงใหม่ ที่มีความรู้ครอบคลุมทั้ง 3 ด้าน:

1. **ผู้เชี่ยวชาญด้านป่าไม้** — เข้าใจจุดความร้อน (hotspot) สาเหตุไฟป่า พื้นที่เสี่ยง ป่าสงวน อุทยาน และการเฝ้าระวัง เหมือนเจ้าหน้าที่จากกรมป่าไม้
2. **นักวิเคราะห์ข้อมูลดาวเทียม** — อ่านค่า PM2.5, ค่าความมั่นใจของจุดความร้อน (confidence), ดาวเทียม VIIRS/MODIS, ทิศทางลม เหมือนตัวแทนจาก GISTDA
3. **ไกด์ท่องเที่ยวเชียงใหม่** — รู้จักสถานที่ท่องเที่ยว ร้านอาหาร คาเฟ่ วัด น้ำตก ดอยต่างๆ ถ้ำ หมู่บ้าน ฤดูกาล เทศกาล วัฒนธรรมล้านนา และแนะนำได้ตามสถานการณ์อากาศจริง

## กฎการตอบ
- **ตอบเป็นภาษาไทยเสมอ** ยกเว้นศัพท์เทคนิคที่จำเป็น (PM2.5, VIIRS, GISTDA)
- **อิงข้อมูลจริง** จาก dashboard ที่ให้มา — อย่าแต่งตัวเลข ถ้าไม่มีข้อมูลให้บอกตรงๆ
- **สั้น กระชับ อ่านง่าย** — ใช้ bullet points, emoji ประกอบเล็กน้อย ไม่ต้องยาวเกินไป
- **แนะนำสถานที่ท่องเที่ยวตามอากาศ** — ถ้า PM2.5 ต่ำ แนะนำกิจกรรมกลางแจ้ง; ถ้าสูง แนะนำในร่ม หรือพื้นที่ที่อากาศดีกว่า
- **เตือนพื้นที่อันตราย** — ถ้ามี hotspot ในอำเภอไหน เตือนอย่าเข้าไป พร้อมแนะนำเส้นทางเลี่ยง
- **น้ำเสียงเป็นมิตร** — เหมือนพี่ที่ห่วงใย ไม่ใช่ราชการ เข้าถึงง่ายทั้งนักท่องเที่ยวและคนท้องถิ่น
- **อย่าพูดว่าคุณเป็น AI** — คุณคือ "คุณเชียงใหม่" ผู้เชี่ยวชาญด้านหมอกควัน
- ถ้าถูกถามเรื่องที่ไม่เกี่ยวกับเชียงใหม่/ฝุ่น/ท่องเที่ยว ให้ตอบสั้นๆ แล้วดึงกลับมาเรื่องสถานการณ์`;

// ─── Dashboard context builder ───────────────────────────────────────────────

function buildDashboardContext(data: DashboardResponse): string {
  const hotspotList = data.hotspots.items
    .map(
      (h) =>
        `- ${h.district || 'ไม่ระบุ'}${h.subdistrict ? ` ต.${h.subdistrict}` : ''}: confidence ${h.confidence}%, ${h.landuse_name || h.landuse_type || 'ไม่ระบุ'}, ${h.satellite || 'VIIRS'}, ${h.detected_at}`,
    )
    .join('\n');

  const stationList = data.pm25.stations
    .map((s) => `- ${s.name || s.id}: PM2.5 = ${s.pm25} µg/m³, อ.${s.district}, trend ${s.trend}`)
    .join('\n');

  return `📊 ข้อมูล Dashboard ณ ตอนนี้:

▸ PM2.5 เฉลี่ยจังหวัด: ${data.pm25.current_pm25} µg/m³ (${data.pm25.category}, สี${data.pm25.color})
▸ แนวโน้ม: ${data.pm25.trend}
▸ สถานีวัด (${data.pm25.stations.length} สถานี):
${stationList}

▸ จุดความร้อนวันนี้: ${data.hotspots.count} จุด (ความหนาแน่น ${data.hotspots.density_per_100_km2}/100km²)
${data.hotspots.items.length > 0 ? `รายละเอียด:\n${hotspotList}` : '(ไม่พบจุดความร้อน)'}

▸ ลม: ${data.weather.wind_speed_kmh} km/h จากทิศ${data.weather.wind_direction_text} (${data.weather.wind_direction_deg}°)
▸ อุณหภูมิ: ${data.weather.temperature_c}°C, ความชื้น: ${data.weather.humidity_percent}%

▸ คะแนนความเสี่ยง: ${data.risk.score}/10 (${data.risk.category})
▸ อัปเดตล่าสุด: ${data.pm25.latest_update}`;
}

// ─── Chat message types ──────────────────────────────────────────────────────

export type ChatRole = 'user' | 'model';

export type ChatMessage = {
  role: ChatRole;
  text: string;
};

// ─── Public API ──────────────────────────────────────────────────────────────

export async function generateDailyBriefing(dashboard: DashboardResponse): Promise<string> {
  if (PROVIDER === 'none') return '';

  const context = buildDashboardContext(dashboard);
  const prompt = `จากข้อมูล Dashboard ด้านล่าง ช่วยสรุปสถานการณ์วันนี้ให้ประชาชนฟังหน่อย แบบสั้นกระชับ (ไม่เกิน 150 คำ) โดย:
1. สรุปสถานการณ์ฝุ่นและจุดความร้อน
2. แนะนำ 1-2 สถานที่ท่องเที่ยวเชียงใหม่ที่เหมาะกับสภาพอากาศวันนี้ (ระบุชื่อจริง ไม่ใช่ generic)
3. ถ้ามี hotspot ให้เตือนพื้นที่ที่ควรหลีกเลี่ยง
4. คำแนะนำปิดท้ายสั้นๆ

${context}`;

  return callAI([{ role: 'user', content: prompt }], 800);
}

export async function chatWithAdvisor(
  dashboard: DashboardResponse,
  history: ChatMessage[],
  userMessage: string,
): Promise<string> {
  if (PROVIDER === 'none') {
    return 'กรุณาตั้งค่า API key ใน frontend/.env\n• Groq (แนะนำ): VITE_GROQ_API_KEY=gsk_...\n• Gemini: VITE_GEMINI_API_KEY=AIzaSy...';
  }

  const context = buildDashboardContext(dashboard);
  const systemWithContext = `${SYSTEM_PROMPT}\n\n[ข้อมูล Dashboard ล่าสุด]\n${context}`;

  const messages: Array<{ role: string; content: string }> = [];

  // First turn or continued conversation
  for (const msg of history) {
    messages.push({
      role: msg.role === 'user' ? 'user' : 'assistant',
      content: msg.text,
    });
  }
  messages.push({ role: 'user', content: userMessage });

  return callAI(messages, 600, systemWithContext);
}

// ─── Unified AI caller (Groq or Gemini) ─────────────────────────────────────

async function callAI(
  messages: Array<{ role: string; content: string }>,
  maxTokens: number,
  systemOverride?: string,
): Promise<string> {
  if (PROVIDER === 'groq') {
    return callGroq(messages, maxTokens, systemOverride);
  }
  return callGemini(messages, maxTokens, systemOverride);
}

// ─── Groq (OpenAI-compatible) ────────────────────────────────────────────────

async function callGroq(
  messages: Array<{ role: string; content: string }>,
  maxTokens: number,
  systemOverride?: string,
): Promise<string> {
  const allMessages = [
    { role: 'system', content: systemOverride ?? SYSTEM_PROMPT },
    ...messages,
  ];

  const response = await fetch(GROQ_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${GROQ_KEY}`,
    },
    body: JSON.stringify({
      model: GROQ_MODEL,
      messages: allMessages,
      max_tokens: maxTokens,
      temperature: 0.85,
      top_p: 0.92,
    }),
  });

  if (!response.ok) {
    if (response.status === 429) throw new Error('QUOTA_EXCEEDED');
    const errText = await response.text().catch(() => '');
    throw new Error(`Groq API error ${response.status}: ${errText}`);
  }

  const result = await response.json();
  return result.choices?.[0]?.message?.content ?? '';
}

// ─── Gemini ──────────────────────────────────────────────────────────────────

async function callGemini(
  messages: Array<{ role: string; content: string }>,
  maxTokens: number,
  systemOverride?: string,
): Promise<string> {
  // Convert OpenAI-style messages to Gemini format
  const contents = messages.map((m) => ({
    role: m.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: m.content }],
  }));

  const body = {
    system_instruction: { parts: [{ text: systemOverride ?? SYSTEM_PROMPT }] },
    contents,
    generationConfig: {
      temperature: 0.85,
      maxOutputTokens: maxTokens,
      topP: 0.92,
    },
  };

  const response = await fetch(GEMINI_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    if (response.status === 429) throw new Error('QUOTA_EXCEEDED');
    const errText = await response.text().catch(() => '');
    throw new Error(`Gemini API error ${response.status}: ${errText}`);
  }

  const result = await response.json();
  return result.candidates?.[0]?.content?.parts?.[0]?.text ?? '';
}
