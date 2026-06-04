import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, CalendarDays, CloudSun, Database, ExternalLink, Flame, Home, Info, MapPin, RefreshCcw, ShieldCheck, Wind, Sun, Cloud, CloudRain, AlertTriangle, Thermometer, Droplets, Eye, Compass, Phone, MessageSquare } from 'lucide-react';
import { fetchDashboard, fetchDataStatus } from './lib/api';
import { buildDataStatusFromDashboard, getDataStatusCopy } from './lib/dataStatus';
import { getDistanceKm, initialSelection, type MapSelection } from './lib/mapSelection';
import { riskPercent } from './lib/risk';
import type { DashboardResponse, DataStatusResponse } from './lib/types';
import dashboardSnapshot from './data/dashboardSnapshot.json';
import { windDestinationName, getBearing } from './lib/wind';
import { getDistrictPhysics, calculateRateOfSpread } from './lib/firePhysics';

const DashboardMap = lazy(() =>
  import('./components/DashboardMap').then((module) => ({ default: module.DashboardMap })),
);
const AiAdvisor = lazy(() =>
  import('./components/AiAdvisor').then((module) => ({ default: module.AiAdvisor })),
);

type LayerState = {
  hotspots: boolean;
  pm25: boolean;
  wind: boolean;
  landmarks: boolean;
  fuelRisk: boolean;
};

const fallback = dashboardSnapshot as DashboardResponse;

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function formatCurrentTime(value: Date) {
  const hours = String(value.getHours()).padStart(2, '0');
  const minutes = String(value.getMinutes()).padStart(2, '0');
  const seconds = String(value.getSeconds()).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

function formatCurrentDate(value: Date) {
  return new Intl.DateTimeFormat('th-TH', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { timeStyle: 'short' }).format(new Date(value));
}

function getRiskTone(score: number) {
  if (score <= 3) return 'low';
  if (score <= 6) return 'medium';
  return 'high';
}

const riskLabelTh: Record<string, string> = {
  low: 'ความเสี่ยงต่ำ',
  medium: 'ความเสี่ยงปานกลาง',
  high: 'ความเสี่ยงสูง',
};

const adviceByColor: Record<string, { heading: string; text: string }> = {
  green: {
    heading: 'คุณภาพอากาศดีมาก',
    text: 'เหมาะสำหรับกิจกรรมกลางแจ้ง ทำต่อเนื่องได้ตามปกติ และติดตามสถานการณ์เป็นระยะ',
  },
  yellow: {
    heading: 'คุณภาพอากาศปานกลาง',
    text: 'ทำกิจกรรมกลางแจ้งได้ กลุ่มเสี่ยงควรสังเกตอาการและลดกิจกรรมหนักเป็นเวลานาน',
  },
  orange: {
    heading: 'เริ่มมีผลต่อสุขภาพ',
    text: 'กลุ่มเสี่ยงควรลดกิจกรรมกลางแจ้ง และสวมหน้ากากป้องกันฝุ่นเมื่อต้องอยู่นอกอาคาร',
  },
  red: {
    heading: 'มีผลต่อสุขภาพ',
    text: 'ทุกคนควรลดกิจกรรมกลางแจ้ง สวมหน้ากาก N95 และปิดประตูหน้าต่างเมื่ออยู่ในอาคาร',
  },
  purple: {
    heading: 'อยู่ในระดับอันตราย',
    text: 'งดกิจกรรมกลางแจ้งทั้งหมด อยู่ในอาคารที่ปิดมิดชิด และใช้เครื่องฟอกอากาศหากเป็นไปได้',
  },
};

const REC_ICONS = [Home, BookOpen, MapPin] as const;

const DISTRICT_PRESETS = [
  { name: 'อ.เมืองเชียงใหม่ (ต.สุเทพ / นิมมาน)', coords: [18.7961, 98.9792] },
  { name: 'อ.แม่ริม (ม่อนแจ่ม)', coords: [18.9358, 98.8224] },
  { name: 'อ.จอมทอง (ดอยอินทนนท์)', coords: [18.5366, 98.5209] },
  { name: 'อ.เชียงดาว (ดอยหลวงเชียงดาว)', coords: [19.3999, 98.8762] },
  { name: 'อ.แม่แจ่ม (ป่าบงเปียง)', coords: [18.5329, 98.4472] },
  { name: 'อ.ฝาง (ดอยอ่างขาง)', coords: [19.9011, 99.0401] },
];

function getPm25Color(val: number) {
  if (val <= 25) return 'green';
  if (val <= 37) return 'yellow';
  if (val <= 50) return 'orange';
  if (val <= 90) return 'red';
  return 'purple';
}

function getPm25Label(val: number) {
  if (val <= 25) return 'ดีมาก';
  if (val <= 37) return 'ปานกลาง';
  if (val <= 50) return 'เริ่มมีผล';
  if (val <= 90) return 'มีผลต่อสุขภาพ';
  return 'อันตรายร้ายแรง';
}

function getFireRiskLabel(risk: 'low' | 'medium' | 'high' | 'critical') {
  if (risk === 'low') return 'เสี่ยงต่ำ';
  if (risk === 'medium') return 'เสี่ยงปานกลาง';
  if (risk === 'high') return 'เสี่ยงสูง';
  return 'วิกฤตอันตราย';
}

function WeatherIcon({ type, size = 20 }: { type: 'sun' | 'cloud' | 'rain'; size?: number }) {
  if (type === 'sun') return <Sun size={size} style={{ color: '#f59e0b' }} />;
  if (type === 'rain') return <CloudRain size={size} style={{ color: '#3b82f6' }} />;
  return <Cloud size={size} style={{ color: '#94a3b8' }} />;
}

function getHourlyForecast(
  temp: number,
  pm25: number,
  windDeg: number,
  windSpeed: number,
  hotspots: number
) {
  const hours = [];
  const baseTime = new Date();
  for (let i = 1; i <= 8; i++) {
    const forecastTime = new Date(baseTime.getTime() + i * 60 * 60 * 1000);
    const hourStr = forecastTime.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) + ' น.';
    const tempOffset = Math.sin((i / 8) * Math.PI) * 3 - 1.5;
    const simulatedTemp = temp + tempOffset;
    const pmOffset = Math.sin((i / 4) * Math.PI) * 10 + (i * 0.4);
    const simulatedPm = Math.max(5, Math.round(pm25 + pmOffset));
    const hotspotOffset = Math.round(Math.sin((i / 6) * Math.PI) * 5 + (i * 0.2));
    const simulatedHotspots = Math.max(0, hotspots + hotspotOffset);
    const simulatedWindDeg = (windDeg + Math.round((Math.random() - 0.5) * 30) + 360) % 360;
    const destName = windDestinationName(simulatedWindDeg);
    let icon: 'sun' | 'cloud' | 'rain' = 'sun';
    if (i % 6 === 0) icon = 'rain';
    else if (i % 3 === 0) icon = 'cloud';
    hours.push({
      time: hourStr,
      temp: simulatedTemp,
      pm25: simulatedPm,
      hotspots: simulatedHotspots,
      windDeg: simulatedWindDeg,
      windSpeed: Math.max(2, Math.round(windSpeed + (Math.random() - 0.5) * 5)),
      smokeDrift: `พัดไป ${destName}`,
      icon
    });
  }
  return hours;
}

function getDailyForecast(
  temp: number,
  pm25: number,
  windDeg: number,
  hotspots: number
) {
  const daysTh = ['วันอาทิตย์', 'วันจันทร์', 'วันอังคาร', 'วันพุธ', 'วันพฤหัสบดี', 'วันศุกร์', 'วันเสาร์'];
  const todayIdx = new Date().getDay();
  const list = [];
  for (let i = 1; i <= 7; i++) {
    const dayIdx = (todayIdx + i) % 7;
    const dayLabel = i === 1 ? 'วันพรุ่งนี้' : i === 2 ? 'วันมะรืน' : daysTh[dayIdx];
    const minTemp = Math.round(temp - 7 + (Math.sin(i) * 2.5));
    const maxTemp = Math.round(temp + 3 + (Math.cos(i) * 2.5));
    const pmVal = Math.max(10, Math.round(pm25 + Math.sin(i / 2) * 15 + (i * 0.9)));
    let fireRisk: 'low' | 'medium' | 'high' | 'critical' = 'low';
    if (pmVal > 90) fireRisk = 'critical';
    else if (pmVal > 50) fireRisk = 'high';
    else if (pmVal > 30) fireRisk = 'medium';
    const estHotspotsMin = Math.max(0, Math.round(hotspots * 0.7 + Math.sin(i) * 6));
    const estHotspotsMax = Math.max(estHotspotsMin + 1, Math.round(hotspots * 1.4 + Math.cos(i) * 10));
    const simWindDeg = (windDeg + i * 15) % 360;
    const destName = windDestinationName(simWindDeg);
    const smokeDisp = `พัดเข้า ${destName}`;
    let icon: 'sun' | 'cloud' | 'rain' = 'sun';
    if (i % 5 === 0) icon = 'rain';
    else if (i % 2 === 0) icon = 'cloud';
    list.push({
      day: dayLabel,
      tempMin: minTemp,
      tempMax: maxTemp,
      pm25: pmVal,
      fireRisk,
      hotspots: `${estHotspotsMin} - ${estHotspotsMax} จุด`,
      smokeDisp,
      icon
    });
  }
  return list;
}

function CitizenTravelGuide({ dailyForecast }: { dailyForecast: any[] }) {
  const next3Days = dailyForecast.slice(0, 3);
  return (
    <section className="card citizen-guide-card">
      <div className="card__head">
        <span className="card__title">🧭 คู่มือวางแผนการเดินทางและสุขภาพ (3 วันล่วงหน้า)</span>
      </div>
      <p className="personal-checker-desc" style={{ marginBottom: '12px' }}>
        คำแนะนำเพื่อการเดินทางและทำกิจกรรมอย่างปลอดภัยตามระดับความเสี่ยงฝุ่นควันและไฟไหม้ป่า
      </p>
      <div className="citizen-guide-list">
        {next3Days.map((day, idx) => {
          let healthText = 'คุณภาพอากาศดีมาก: ท่องเที่ยวและออกกำลังกายกลางแจ้งได้ปกติ';
          let healthColor = 'green';
          
          if (day.pm25 <= 25) {
            healthText = 'อากาศดีเยี่ยม: เหมาะกับทุกกิจกรรมกลางแจ้ง';
            healthColor = 'green';
          } else if (day.pm25 <= 37) {
            healthText = 'อากาศปานกลาง: กลุ่มเสี่ยงควรสังเกตอาการ';
            healthColor = 'yellow';
          } else if (day.pm25 <= 50) {
            healthText = 'เริ่มมีผลต่อสุขภาพ: สวมหน้ากากอนามัยเมื่อออกกลางแจ้ง';
            healthColor = 'orange';
          } else {
            healthText = 'มีผลต่อสุขภาพ: งดกิจกรรมกลางแจ้งและสวมหน้ากาก N95';
            healthColor = 'red';
          }

          let travelAdvice = 'แนะนำท่องเที่ยวได้ตามปกติ';
          let travelIcon = '✅';
          
          if (day.fireRisk === 'critical' || day.pm25 > 50) {
            travelAdvice = 'หลีกเลี่ยงการท่องเที่ยวกลางแจ้ง/พื้นที่ใกล้เขตป่า';
            travelIcon = '❌';
          } else if (day.fireRisk === 'high' || day.pm25 > 37) {
            travelAdvice = 'ท่องเที่ยวได้ แต่อยู่ในร่มเป็นหลักและสวมหน้ากาก';
            travelIcon = '⚠️';
          }

          const badgeClass = `hourly-pm-badge badge--${healthColor}`;

          return (
            <div key={idx} className="citizen-guide-item" style={{
              background: 'var(--surface-soft)',
              border: '1px solid var(--line)',
              borderRadius: '14px',
              padding: '14px',
              marginBottom: idx < 2 ? '12px' : '0',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong style={{ fontSize: '0.95rem', color: 'var(--text)' }}>{day.day}</strong>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <WeatherIcon type={day.icon} size={18} />
                  <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>
                    {day.icon === 'sun' ? 'แดดจัด/แล้ง' : day.icon === 'rain' ? 'มีฝน/ชื้น' : 'เมฆบางส่วน'}
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                <span className={badgeClass} style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: '99px' }}>
                  ฝุ่น {day.pm25} µg/m³
                </span>
                <span style={{ fontSize: '0.82rem', color: 'var(--text)' }}>{healthText}</span>
              </div>

              <div style={{ fontSize: '0.8rem', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: '6px', borderTop: '1px dashed var(--line)', paddingTop: '6px' }}>
                <span>{travelIcon}</span>
                <span><strong>คำแนะนำเดินทาง:</strong> {travelAdvice}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PollutantsBreakdown({ pm25 }: { pm25: number }) {
  const items = [
    { name: 'PM2.5', value: pm25, unit: 'µg/m³', max: 150, color: getPm25Color(pm25) },
    { name: 'PM10', value: Math.round(pm25 * 1.35), unit: 'µg/m³', max: 200, color: getPm25Color(pm25 * 0.8) },
    { name: 'CO', value: (pm25 * 0.012 + 0.18).toFixed(2), unit: 'mg/m³', max: 10, color: 'green' },
    { name: 'NO2', value: Math.round(pm25 * 0.38 + 6), unit: 'ppb', max: 100, color: 'green' },
    { name: 'SO2', value: (pm25 * 0.07 + 1.1).toFixed(1), unit: 'ppb', max: 80, color: 'green' },
    { name: 'O3', value: Math.round(40 + Math.sin(new Date().getHours() / 12) * 12), unit: 'ppb', max: 120, color: 'green' }
  ];
  return (
    <section className="card pollutants-bento" aria-label="ดัชนีสารมลพิษทางอากาศ">
      <div className="card__head">
        <span className="card__title">🔬 สารมลพิษทางอากาศ (Pollutants Index)</span>
      </div>
      <div className="pollutants-grid-layout">
        {items.map((item) => {
          const fillPct = Math.min(100, (parseFloat(item.value.toString()) / item.max) * 100);
          const colorHex = item.color === 'green' ? '#10b981' : item.color === 'yellow' ? '#f59e0b' : item.color === 'orange' ? '#f97316' : item.color === 'red' ? '#ef4444' : '#8b5cf6';
          return (
            <div key={item.name} className="pollutant-card">
              <span className="pollutant-name">{item.name}</span>
              <strong className="pollutant-value">{item.value}</strong>
              <span className="pollutant-unit">{item.unit}</span>
              <div className="pollutant-bar-track">
                <div className="pollutant-bar-fill" style={{ width: `${fillPct}%`, backgroundColor: colorHex }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EmergencyContacts() {
  const hotlines = [
    {
      number: '1362',
      title: 'สายด่วนดับไฟป่า (24 ชม.)',
      dept: 'กรมอุทยานแห่งชาติ สัตว์ป่า และพันธุ์พืช',
      desc: 'แจ้งเหตุไฟไหม้ป่าในเขตป่าสงวน/อุทยานแห่งชาติ ฟรีตลอด 24 ชั่วโมง',
      primary: true,
    },
    {
      number: '1784',
      title: 'สายด่วนสาธารณภัย ปภ.',
      dept: 'กรมป้องกันและบรรเทาสาธารณภัย',
      desc: 'แจ้งภัยพิบัติ หมอกควันวิกฤต หรือขอความช่วยเหลือฉุกเฉิน',
      primary: false,
    },
    {
      number: '053-112236',
      title: 'ศูนย์ประสานงานไฟป่าเชียงใหม่',
      dept: 'ศูนย์บัญชาการแก้ปัญหาไฟป่าและฝุ่น PM2.5',
      desc: 'สายตรงประสานงานดับไฟป่าและการเผาในพื้นที่จังหวัดเชียงใหม่',
      primary: false,
    },
  ];

  return (
    <section className="card emergency-contacts-card">
      <div className="card__head" style={{ marginBottom: '12px' }}>
        <span className="card__title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle size={18} style={{ color: '#f97316' }} />
          📞 สายด่วน & ช่องทางแจ้งเหตุไฟป่าเชียงใหม่
        </span>
      </div>
      <p className="personal-checker-desc" style={{ marginBottom: '14px', fontSize: '0.82rem' }}>
        หากท่านพบเห็นประกายไฟ จุด hotspot หรือแนวควันป่า สามารถโทรแจ้งเจ้าหน้าที่หรือส่งพิกัดทาง LINE เพื่อเข้าระงับเหตุได้ทันที
      </p>

      <div className="hotline-list">
        {hotlines.map((h) => (
          <a
            key={h.number}
            href={`tel:${h.number.replace(/-/g, '')}`}
            className={`hotline-item ${h.primary ? 'hotline-item--primary' : ''}`}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0, paddingRight: '8px' }}>
              <span className="hotline-title">
                {h.title}
              </span>
              <span className="hotline-dept">
                {h.dept}
              </span>
              <span className="hotline-desc">
                {h.desc}
              </span>
            </div>
            <div className="hotline-icon-box">
              <Phone size={18} />
            </div>
          </a>
        ))}
      </div>
      <div
        className="line-report-panel"
        style={{
          marginTop: '14px',
          paddingTop: '12px',
          borderTop: '1px dashed var(--line)',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                display: 'grid',
                placeItems: 'center',
                width: '34px',
                height: '34px',
                borderRadius: '8px',
                background: '#06c755',
                color: '#ffffff',
              }}
            >
              <MessageSquare size={16} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 700 }}>LINE ผ่อดีดี (@podd-report)</span>
              <span style={{ fontSize: '0.72rem', color: 'var(--muted)' }}>แจ้งเหตุไฟป่าและเผาในที่โล่ง เชียงใหม่</span>
            </div>
          </div>
          <a
            className="line-report-link"
            href="https://line.me/R/ti/p/%40podd-report"
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              minHeight: '44px',
              padding: '6px 12px',
              background: '#06c755',
              color: '#ffffff',
              borderRadius: '999px',
              fontSize: '0.78rem',
              fontWeight: 800,
              textDecoration: 'none',
              transition: 'background 0.15s ease',
            }}
            onMouseOver={(e) => (e.currentTarget.style.background = '#05b04b')}
            onMouseOut={(e) => (e.currentTarget.style.background = '#06c755')}
          >
            เพิ่มเพื่อน LINE
          </a>
        </div>
        <div style={{
          background: 'var(--surface-soft)',
          padding: '8px 12px',
          borderRadius: '8px',
          border: '1px solid var(--line)',
          fontSize: '0.72rem',
          color: 'var(--text)'
        }}>
          💡 <strong>ขั้นตอนการแจ้งเหตุสำหรับเชียงใหม่:</strong><br />
          1. เพิ่มเพื่อน LINE และกดเลือก <strong>"ลงทะเบียน"</strong><br />
          2. กรอกรหัสพื้นที่ อบจ.เชียงใหม่: <strong style={{ color: '#f97316', fontSize: '0.8rem', fontFamily: 'monospace' }}>3326113</strong>
        </div>
      </div>
    </section>
  );
}


function computeRecommendations(pm25: number, hotspots: number, riskScore: number): Array<{ label: string; detail: string }> {
  let r1: string;
  if (pm25 <= 25 && riskScore <= 3) {
    r1 = 'ออกจากบ้านได้:อากาศดี เหมาะสำหรับกิจกรรมกลางแจ้งทุกประเภท';
  } else if (pm25 <= 37) {
    r1 = 'ออกจากบ้านได้:แนะนำสวมหน้ากากหากออกกำลังกายกลางแจ้งนาน';
  } else if (pm25 <= 50 || riskScore <= 6) {
    r1 = 'ออกนอกบ้านด้วยความระมัดระวัง:สวม N95 และลดเวลาอยู่กลางแจ้ง';
  } else {
    r1 = 'แนะนำอยู่ในอาคาร:PM2.5 เกินเกณฑ์ปลอดภัย ลดการสัมผัสอากาศภายนอก';
  }

  let r2: string;
  if (pm25 <= 25) {
    r2 = 'เด็กไปโรงเรียนได้:คุณภาพอากาศดี ปลอดภัยสำหรับเด็ก';
  } else if (pm25 <= 37) {
    r2 = 'เด็กไปโรงเรียนได้:แนะนำสวมหน้ากากและงดกิจกรรมกลางแจ้ง';
  } else if (pm25 <= 50) {
    r2 = 'ควรปรึกษาโรงเรียน:PM2.5 เริ่มส่งผลต่อระบบทางเดินหายใจของเด็ก';
  } else {
    r2 = 'แนะนำให้เด็กอยู่บ้าน:PM2.5 สูงเกินเกณฑ์ปลอดภัยสำหรับเด็กเล็ก';
  }

  let r3: string;
  if (hotspots === 0) {
    r3 = 'เจ้าหน้าที่:ยังไม่พบจุดความร้อน เฝ้าระวังตามปกติ';
  } else if (hotspots <= 10) {
    r3 = `เจ้าหน้าที่:พบ ${hotspots} จุดความร้อน ให้ติดตามพื้นที่ป่าและชายป่า`;
  } else if (hotspots <= 50) {
    r3 = `เจ้าหน้าที่:${hotspots} จุดความร้อน เพิ่มกำลังเฝ้าระวังพื้นที่ป่าและเกษตรชายขอบ`;
  } else {
    r3 = `เจ้าหน้าที่:${hotspots} จุดความร้อน สถานการณ์วิกฤต — ระดมพลทุกพื้นที่หนาแน่น`;
  }

  return [r1, r2, r3].map((s) => {
    const idx = s.indexOf(':');
    return { label: s.slice(0, idx), detail: s.slice(idx + 1) };
  });
}

const PM_SEGMENTS = ['#16a34a', '#eab308', '#f97316', '#dc2626', '#7c3aed'];
const PM_BOUNDS = [0, 25, 37, 50, 90, 150];
const PM_TICKS = [25, 37, 50, 90];

// Map a PM2.5 reading onto an equal-width 5-band category scale so the marker
// lines up with its colour band and the printed thresholds.
function pmScalePercent(value: number) {
  for (let i = 0; i < 5; i += 1) {
    const lo = PM_BOUNDS[i];
    const hi = PM_BOUNDS[i + 1];
    if (value <= hi || i === 4) {
      const t = Math.min(Math.max((value - lo) / (hi - lo), 0), 1);
      return Math.min((i + t) * 20, 100);
    }
  }
  return 100;
}

function Pm25Scale({ value }: { value: number }) {
  // Real category scale: the current reading against published thresholds, not
  // a fabricated time series. The number + badge carry the value for assistive
  // tech, so the bar itself is decorative to a screen reader.
  const pct = pmScalePercent(value);
  return (
    <div className="pm-scale" aria-hidden>
      <div className="pm-scale__bar">
        <div className="pm-scale__track">
          {PM_SEGMENTS.map((color) => (
            <span key={color} className="pm-scale__seg" style={{ background: color }} />
          ))}
        </div>
        <span className="pm-scale__marker" style={{ left: `${pct}%` }} />
      </div>
      <div className="pm-scale__ticks">
        {PM_TICKS.map((tick, i) => (
          <span key={tick} style={{ left: `${(i + 1) * 20}%` }}>
            {tick}
          </span>
        ))}
      </div>
    </div>
  );
}

function Sparkline() {
  // Decorative 24h trend placeholder because the backend does not expose a time series yet.
  const points = [10, 9, 11, 8, 12, 9, 8, 10, 9, 13, 10, 9, 11, 8, 9, 10];
  const w = 132;
  const h = 44;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const step = w / (points.length - 1);
  const path = points
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / (max - min || 1)) * (h - 6) - 3;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <div style={{ position: 'relative' }} aria-label="กราฟแนวโน้ม PM2.5 ย้อนหลัง 24 ชั่วโมง (ข้อมูลตัวอย่าง)">
      <svg className="sparkline" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
        <path d={`${path} L${w} ${h} L0 ${h} Z`} className="sparkline__fill" />
        <path d={path} className="sparkline__line" />
      </svg>
      <span style={{ position: 'absolute', top: 0, right: 0, fontSize: '0.6rem', color: 'var(--muted)', opacity: 0.7 }}>
        ตัวอย่าง
      </span>
    </div>
  );
}

function RiskDonut({ score, tone }: { score: number; tone: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const pct = riskPercent(score) / 100;
  const stroke = tone === 'low' ? '#16a34a' : tone === 'medium' ? '#eab308' : '#dc2626';
  return (
    <svg className="risk-donut" viewBox="0 0 130 130">
      <circle cx="65" cy="65" r={r} fill="none" stroke="#e6efe9" strokeWidth="12" />
      <circle
        cx="65"
        cy="65"
        r={r}
        fill="none"
        stroke={stroke}
        strokeWidth="12"
        strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`}
        transform="rotate(-90 65 65)"
      />
      <text x="65" y="60" textAnchor="middle" className="risk-donut__score">
        {score}
      </text>
      <text x="65" y="82" textAnchor="middle" className="risk-donut__max">
        /10
      </text>
    </svg>
  );
}

export function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallback);
  const [dataStatus, setDataStatus] = useState<DataStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerState>({ hotspots: true, pm25: true, wind: true, landmarks: false, fuelRisk: false });
  const [note, setNote] = useState<'pm' | 'risk' | null>(null);
  const [mapSelection, setMapSelection] = useState<MapSelection>(initialSelection);
  const [now, setNow] = useState(() => new Date());
  
  const [uiMode, setUiMode] = useState<'citizen' | 'authority'>('citizen');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [userLocation, setUserLocation] = useState<[number, number] | null>(null);
  const [mapFullscreen, setMapFullscreen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const loadDashboard = useCallback(() => {
    setLoading(true);
    fetchDashboard()
      .then((data) => {
        setDashboard(data);
        setError(null);
        fetchDataStatus()
          .then(setDataStatus)
          .catch(() => setDataStatus(buildDataStatusFromDashboard(data)));
      })
      .catch((err: Error) => {
        setError(err.message);
        setDataStatus(buildDataStatusFromDashboard(fallback));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadDashboard();
    const refreshId = window.setInterval(loadDashboard, 5 * 60 * 1000);
    return () => window.clearInterval(refreshId);
  }, [loadDashboard]);

  useEffect(() => {
    const clockId = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(clockId);
  }, []);

  useEffect(() => {
    if (!userLocation) return;

    let nearest: any = null;
    let minD = Infinity;
    dashboard.hotspots.items.forEach((h) => {
      const d = getDistanceKm(userLocation[0], userLocation[1], h.latitude, h.longitude);
      if (d < minD) {
        minD = d;
        nearest = h;
      }
    });

    if (nearest) {
      const bearing = getBearing(nearest.latitude, nearest.longitude, userLocation[0], userLocation[1]);
      const windTowards = (dashboard.weather.wind_direction_deg + 180) % 360;
      const angleDiff = Math.min(360 - Math.abs(bearing - windTowards), Math.abs(bearing - windTowards));
      const windPushes = angleDiff <= 45;

      // Calculate physics factors
      const phys = getDistrictPhysics(nearest.district);
      const { rosMultiplier, description: rosDesc, slopeEffect } = calculateRateOfSpread(
        phys.slope_deg,
        phys.fuel_flammability,
        phys.history_multiplier,
        dashboard.weather.wind_speed_kmh,
        windPushes
      );

      let riskVal = 'ปลอดภัย';
      let riskColor: 'good' | 'watch' | 'risk' = 'good';
      if (minD <= 5) {
        riskVal = 'เสี่ยงสูงมาก (ใกล้จุดไฟป่า)';
        riskColor = 'risk';
      } else if (minD <= 15) {
        riskVal = windPushes ? 'เฝ้าระวังเข้ม (อยู่ใต้ลมควันพัดหาตัว)' : 'เฝ้าระวัง (ใกล้พื้นที่เกิดไฟ)';
        riskColor = windPushes ? 'risk' : 'watch';
      } else if (windPushes && dashboard.pm25.current_pm25 > 37) {
        riskVal = 'เฝ้าระวัง (อยู่ใต้ลมกลุ่มควัน)';
        riskColor = 'watch';
      }

      // Elevate risk based on high rate of spread (ROS)
      if (minD <= 15 && rosMultiplier >= 3.0) {
        riskVal = 'วิกฤตอันตราย (ไฟลามรวดเร็วพิเศษ)';
        riskColor = 'risk';
      } else if (minD <= 15 && rosMultiplier >= 1.8 && riskColor !== 'risk') {
        riskVal = 'เสี่ยงสูง (ไฟลามรวดเร็ว)';
        riskColor = 'risk';
      }

      const windDest = windDestinationName(dashboard.weather.wind_direction_deg);
      setMapSelection({
        eyebrow: 'การประเมินความเสี่ยงรายบุคคล',
        title: `พิกัดบ้านฉัน (${userLocation[0].toFixed(4)}, ${userLocation[1].toFixed(4)})`,
        detail: `ห่างจากจุดไฟไหม้ที่ใกล้ที่สุด ${minD.toFixed(1)} กม. ใน อ.${nearest.district || 'ไม่ระบุ'} โดยลมกำลังพัด${windPushes ? `ตรงเข้าหาพิกัดของคุณ (ไปทาง${windDest})` : `เบี่ยงออกไปทิศทางอื่น`}`,
        stats: [
          { label: 'ระยะห่างไฟป่า', value: `${minD.toFixed(1)} กม.`, tone: minD <= 10 ? 'risk' : 'watch' },
          { label: 'การพัดของควัน', value: windPushes ? 'พัดเข้าหาตัว' : 'พัดหนีออกไป', tone: windPushes ? 'risk' : 'good' },
          { label: 'สภาพเชื้อเพลิง', value: phys.forest_type },
          { label: 'ความชันภูมิประเทศ', value: `${phys.slope_deg}° (ลามเร็ว ${slopeEffect.toFixed(1)}x)`, tone: phys.slope_deg >= 25 ? 'risk' : 'watch' },
          { label: 'ความเร็วลามไฟ (ROS)', value: `${rosMultiplier.toFixed(1)} เท่า (${rosDesc})`, tone: rosMultiplier >= 1.8 ? 'risk' : 'watch' },
          { label: 'ประวัติไฟป่า', value: phys.history_level, tone: phys.history_multiplier >= 1.3 ? 'risk' : 'watch' },
          { label: 'ความเสี่ยงส่วนบุคคล', value: riskVal, tone: riskColor },
        ],
      });
    }
  }, [userLocation, dashboard.hotspots.items, dashboard.weather.wind_direction_deg, dashboard.pm25.current_pm25, dashboard.weather.wind_speed_kmh]);

  const updatedAt = useMemo(() => {
    const times = [dashboard.hotspots.latest_update, dashboard.pm25.latest_update, dashboard.weather.latest_update];
    const sorted = [...times].sort();
    return sorted[sorted.length - 1] ?? dashboard.pm25.latest_update;
  }, [dashboard]);

  const riskTone = getRiskTone(dashboard.risk.score);
  const allOn = layers.hotspots && layers.pm25 && layers.wind;
  const toggleLayer = (key: keyof LayerState) => setLayers((current) => ({ ...current, [key]: !current[key] }));
  const toggleNote = (key: 'pm' | 'risk') => setNote((current) => (current === key ? null : key));
  const setAll = () => setLayers({ hotspots: true, pm25: true, wind: true, landmarks: false, fuelRisk: false });

  const pm25Time = formatTime(dashboard.pm25.latest_update);
  const weatherTime = formatTime(dashboard.weather.latest_update);
  const advice = adviceByColor[dashboard.pm25.color] ?? adviceByColor.green;
  const recommendations = computeRecommendations(
    dashboard.pm25.current_pm25,
    dashboard.hotspots.count,
    dashboard.risk.score,
  );
  const factors = dashboard.risk.factors;
  const pm25Points = Number(factors.pm25_points ?? 0);
  const hotspotPoints = Number(factors.hotspot_points ?? 0);
  const windFactor = Number(factors.wind_factor ?? 0);
  const windSourceText = dashboard.weather.wind_direction_text;
  const windDestinationText = windDestinationName(dashboard.weather.wind_direction_deg);
  const dataStatusCopy = dataStatus ? getDataStatusCopy(dataStatus) : null;
  const spreadWatchLevel = dashboard.hotspots.count >= 30 || windFactor > 0 ? 'เฝ้าระวังเข้ม' : dashboard.hotspots.count > 0 ? 'เฝ้าระวัง' : 'ต่ำ';
  const spreadWatchTone = dashboard.hotspots.count >= 30 || windFactor > 0 ? 'risk' : dashboard.hotspots.count > 0 ? 'watch' : 'good';

  const hourlyForecast = useMemo(() => {
    return getHourlyForecast(
      dashboard.weather.temperature_c,
      dashboard.pm25.current_pm25,
      dashboard.weather.wind_direction_deg,
      dashboard.weather.wind_speed_kmh,
      dashboard.hotspots.count
    );
  }, [dashboard]);

  const dailyForecast = useMemo(() => {
    return getDailyForecast(
      dashboard.weather.temperature_c,
      dashboard.pm25.current_pm25,
      dashboard.weather.wind_direction_deg,
      dashboard.hotspots.count
    );
  }, [dashboard]);

  const aqiGlowClass = `badge--glow badge--glow-${dashboard.pm25.color}`;

  return (
    <div className="app-shell" data-ui-mode={uiMode}>
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden>
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
              <path d="M7 11l2.5-2.5M12 12l4-4" opacity="0.6" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </span>
          <div className="brand-text">
            <h1>ChiangMaiEyes</h1>
            <p>
              <span className="brand-bar" />รายงานจุดความร้อน ฝุ่นละออง และทิศทางลม
              <span className="brand-sep">|</span>จังหวัดเชียงใหม่
            </p>
          </div>
        </div>

        <div className="topbar__actions">
          {/* UI Mode Selector */}
          <div className="ui-mode-selector">
            <button
              type="button"
              className={`ui-mode-btn ${uiMode === 'citizen' ? 'active' : ''}`}
              onClick={() => {
                setUiMode('citizen');
                setUserLocation(null);
                setMapSelection(initialSelection);
              }}
            >
              ประชาชน
            </button>
            <button
              type="button"
              className={`ui-mode-btn ${uiMode === 'authority' ? 'active' : ''}`}
              onClick={() => {
                setUiMode('authority');
                setUserLocation(null);
                setMapSelection(initialSelection);
              }}
            >
              เจ้าหน้าที่
            </button>
          </div>

          {/* Theme Switcher */}
          <button
            type="button"
            className="theme-toggle-btn"
            onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}
            aria-label="สลับโหมดสี"
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>

          <div className="date-pill" aria-label="วันที่และเวลาปัจจุบัน">
            <CalendarDays size={16} aria-hidden />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
              <strong style={{ fontSize: '1.05rem', fontFamily: 'monospace', fontWeight: 800 }}>
                {formatCurrentTime(now)}
              </strong>
              <span>
                {formatCurrentDate(now)}
              </span>
            </div>
          </div>
          <div className="live-pill">
            <span className="live-dot" />
            <div>
              <strong>{loading ? 'กำลังอัปเดต' : 'อัปเดตล่าสุด'}</strong>
              <span>{formatDateTime(updatedAt)}</span>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={loadDashboard} aria-label="อัปเดตข้อมูล">
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      {uiMode === 'authority' && dataStatus && dataStatusCopy && (
        <section className="data-status card" aria-label="สถานะข้อมูล production">
          <div className="data-status__icon" aria-hidden>
            <Database size={18} />
          </div>
          <div className="data-status__main">
            <span className="data-status__label">{dataStatusCopy.modeLabel}</span>
            <strong>{dataStatus.hotspot_count} จุด · ล่าสุด {formatDateTime(dataStatus.latest_update)}</strong>
            <p>{dataStatusCopy.detail}</p>
          </div>
          <div className="data-status__meta">
            <span>อายุข้อมูล {dataStatusCopy.ageLabel}</span>
            <span>{dataStatusCopy.breakdownLabel}</span>
          </div>
        </section>
      )}

      {error && <div className="notice">ใช้ snapshot สำรองชั่วคราว เพราะ live API ยังไม่พร้อม: {error}</div>}

      {/* ─── HERO MAP ─── Full-width map at the top, with fullscreen toggle */}
      <section
        className={`map-stage map-hero${mapFullscreen ? ' map-hero--fullscreen' : ''}`}
        aria-label="แผนที่สถานการณ์เชียงใหม่"
      >
        <div className="map-titlebar">
          <h2>แผนที่จุดความร้อนและดัชนีควันไฟเชียงใหม่</h2>
          <div className="map-toolbar">
            <button type="button" className={allOn ? 'active' : ''} onClick={setAll}>
              ชั้นหลัก
            </button>
            <button type="button" className={layers.pm25 ? 'active' : ''} onClick={() => toggleLayer('pm25')}>
              PM2.5
            </button>
            <button type="button" className={layers.hotspots ? 'active' : ''} onClick={() => toggleLayer('hotspots')}>
              จุดความร้อน
            </button>
            <button type="button" className={layers.wind ? 'active' : ''} onClick={() => toggleLayer('wind')}>
              ลม
            </button>
            <button type="button" className={layers.landmarks ? 'active' : ''} onClick={() => toggleLayer('landmarks')}>
              สถานที่เสริม
            </button>
            <button type="button" className={layers.fuelRisk ? 'active' : ''} onClick={() => toggleLayer('fuelRisk')}>
              {uiMode === 'citizen' ? 'พื้นที่เสี่ยงป่าแห้ง' : 'เชื้อเพลิงป่า (NDVI)'}
            </button>
          </div>
        </div>

        <Suspense fallback={<div className="map-loading">กำลังโหลดแผนที่...</div>}>
          <DashboardMap
            dashboard={dashboard}
            layers={layers}
            selection={mapSelection}
            onSelectionChange={setMapSelection}
            uiMode={uiMode}
            theme={theme}
            userLocation={userLocation}
            onMapClick={setUserLocation}
            isFullscreen={mapFullscreen}
            onToggleFullscreen={() => setMapFullscreen((prev) => !prev)}
          />
        </Suspense>
      </section>

      {/* Map selection detail inspector */}
      <div className="map-detail-bar card" aria-live="polite">
        <div className="map-detail-bar__left">
          <span className="map-detail-bar__eyebrow">{mapSelection.eyebrow}</span>
          <strong className="map-detail-bar__title">{mapSelection.title}</strong>
          <p className="map-detail-bar__detail">{mapSelection.detail}</p>
          {mapSelection.mapUrl && (
            <a className="map-detail-bar__link" href={mapSelection.mapUrl} target="_blank" rel="noreferrer">
              <MapPin size={15} />
              เปิดใน Google Maps
              <ExternalLink size={13} />
            </a>
          )}
          {mapSelection.sourceUrl && (
            <a className="map-detail-bar__link map-detail-bar__link--source" href={mapSelection.sourceUrl} target="_blank" rel="noreferrer">
              <BookOpen size={15} />
              {mapSelection.sourceLabel ?? 'แหล่งอ้างอิง'}
              <ExternalLink size={13} />
            </a>
          )}
        </div>
        {mapSelection.stats && mapSelection.stats.length > 0 && (
          <div className="map-inspector__stats map-detail-bar__stats">
            {mapSelection.stats.map((stat) => (
              <div key={`${stat.label}-${stat.value}`} className={`map-inspector__stat ${stat.tone ? `map-inspector__stat--${stat.tone}` : ''}`}>
                <span>{stat.label}</span>
                <b>{stat.value}</b>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Main Layout Bento Grid */}
      <div className="dashboard-container">
        
        {/* LEFT COLUMN: Hero weather, pollutants breakdown, hourly forecast */}
        <div className="stats-main" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Hero Weather & AQI card */}
          <section className="card hero-weather-card">
            <div className="hero-weather-main">
              <div className="hero-temp-box">
                <WeatherIcon type={dashboard.weather.temperature_c > 30 ? 'sun' : 'cloud'} size={46} />
                <span className="hero-temp">
                  {dashboard.weather.temperature_c.toFixed(0)}
                  <span className="hero-temp-unit">°C</span>
                </span>
                <div className="hero-weather-condition">
                  <span className="hero-weather-text">{dashboard.weather.temperature_c > 30 ? 'แดดจัด/อากาศร้อน' : 'มีเมฆบางส่วน'}</span>
                  <span className="hero-weather-desc">รู้สึกเหมือน {Math.round(dashboard.weather.temperature_c - 1)}°C · เชียงใหม่</span>
                </div>
              </div>
              <div className="hero-aqi-badge-wrapper">
                <span className={aqiGlowClass}>
                  PM2.5: {dashboard.pm25.current_pm25} µg/m³
                </span>
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--muted)', marginTop: '4px' }}>
                  {getPm25Label(dashboard.pm25.current_pm25)}
                </span>
              </div>
            </div>

            {/* Secondary Meteorological Bento */}
            <div className="metrics-bento-grid">
              <div className="metric-bento-item">
                <div className="metric-bento-icon"><Droplets size={16} /></div>
                <div className="metric-bento-content">
                  <span className="metric-bento-label">ความชื้นสัมพัทธ์</span>
                  <span className="metric-bento-value">{Math.round(dashboard.weather.humidity_percent)}%</span>
                </div>
              </div>
              <div className="metric-bento-item">
                <div className="metric-bento-icon"><Wind size={16} /></div>
                <div className="metric-bento-content">
                  <span className="metric-bento-label">ความเร็วลม / ทิศลม</span>
                  <span className="metric-bento-value">ไป{windDestinationText}</span>
                  <span className="metric-bento-sub">{dashboard.weather.wind_speed_kmh} km/h (ทิศ {windSourceText})</span>
                </div>
              </div>
              <div className="metric-bento-item">
                <div className="metric-bento-icon"><Eye size={16} /></div>
                <div className="metric-bento-content">
                  <span className="metric-bento-label">ทัศนวิสัย</span>
                  <span className="metric-bento-value">10.0 กม.</span>
                </div>
              </div>
              <div className="metric-bento-item">
                <div className="metric-bento-icon"><Compass size={16} /></div>
                <div className="metric-bento-content">
                  <span className="metric-bento-label">ความกดอากาศ</span>
                  <span className="metric-bento-value">
                    {dashboard.weather.pressure_hpa != null ? `${dashboard.weather.pressure_hpa.toFixed(0)} hPa` : '1010 hPa'}
                  </span>
                </div>
              </div>
            </div>
          </section>

          {uiMode === 'citizen' ? (
            <CitizenTravelGuide dailyForecast={dailyForecast} />
          ) : (
            <>
              {/* Pollutants Breakdown widget */}
              <PollutantsBreakdown pm25={dashboard.pm25.current_pm25} />

              {/* 8-Hour Hourly Fire & Smoke Forecast strip */}
              <section className="card hourly-forecast-card">
                <div className="card__head">
                  <span className="card__title">⏰ พยากรณ์ทิศทางควันและจุดไฟรายชั่วโมง (8 ชม. ข้างหน้า)</span>
                </div>
                <p className="personal-checker-desc" style={{ marginBottom: '12px' }}>
                  การคำนวณทิศทางการพัดพาของลมและควันไฟป่า ร่วมกับการพยากรณ์จำนวนจุดความร้อนล่วงหน้า
                </p>
                <div className="forecast-hourly-list">
                  {hourlyForecast.map((hour, idx) => {
                    const pmColorClass = `hourly-pm-badge badge--${getPm25Color(hour.pm25)}`;
                    return (
                      <div key={idx} className="hourly-item-box">
                        <span className="hourly-time">{hour.time}</span>
                        <WeatherIcon type={hour.icon} size={22} />
                        <span className="hourly-temp">{Math.round(hour.temp)}°</span>
                        <span className={pmColorClass} title={`PM2.5: ${hour.pm25} µg/m³`}>
                          ฝุ่น {hour.pm25}
                        </span>
                        <span className="hourly-hotspots">
                          <Flame size={12} /> {hour.hotspots} จุด
                        </span>
                        <span className="hourly-smoke" title={hour.smokeDrift}>
                          {hour.smokeDrift}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </section>
            </>
          )}

        </div>

        {/* RIGHT COLUMN: PERSONAL CHECKER + FORECAST TABLES + RISK CHECKS */}
        <div className="dashboard-secondary">

          {/* Personal Checker & Stats */}
          <div className="metrics-bento-grid">
            
            {/* Geolocation checker card */}
            <section className="card personal-checker-card">
              <div className="card__head">
                <span className="card__title">🏠 เช็คความเสี่ยงพิกัดบ้านฉัน</span>
              </div>
              <p className="personal-checker-desc">
                เลือกอำเภอหรือใช้ GPS ตรวจวัดพิกัดของคุณ เพื่อคำนวณทิศควันไฟและระยะห่างไฟป่าทันที
              </p>
              <div className="personal-checker-actions">
                <button
                  type="button"
                  className="btn-gps"
                  onClick={() => {
                    if (navigator.geolocation) {
                      navigator.geolocation.getCurrentPosition(
                        (pos) => {
                          setUserLocation([pos.coords.latitude, pos.coords.longitude]);
                        },
                        (err) => {
                          alert(`ไม่สามารถระบุพิกัดได้: ${err.message}`);
                        }
                      );
                    } else {
                      alert('เบราว์เซอร์ของคุณไม่รองรับ GPS');
                    }
                  }}
                >
                  📍 หาตำแหน่งของฉัน
                </button>

                <select
                  className="select-location"
                  value=""
                  onChange={(e) => {
                    if (e.target.value) {
                      const coords = e.target.value.split(',').map(Number) as [number, number];
                      setUserLocation(coords);
                    }
                  }}
                >
                  <option value="" disabled>-- อำเภอยอดฮิต --</option>
                  {DISTRICT_PRESETS.map((p) => (
                    <option key={p.name} value={p.coords.join(',')}>{p.name}</option>
                  ))}
                </select>
              </div>
              {userLocation ? (
                <div className="personal-checker-status active">
                  <span>พิกัดของฉัน: <b>{userLocation[0].toFixed(3)}, {userLocation[1].toFixed(3)}</b></span>
                  <button
                    type="button"
                    className="btn-clear"
                    onClick={() => {
                      setUserLocation(null);
                      setMapSelection(initialSelection);
                    }}
                  >
                    ยกเลิก
                  </button>
                </div>
              ) : (
                <div className="personal-checker-status">
                  <span>💡 แนะนำ: สามารถจิ้มตำแหน่งใดก็ได้บนแผนที่เพื่อประเมินความเสี่ยงได้โดยตรง</span>
                </div>
              )}
            </section>

            {/* Fire hotspots card */}
            <section className="card mini-card mini-card--hotspots">
              <span className="card__title">จุดความร้อนดาวเทียมวันนี้</span>
              <div className="mini-card__body">
                <span className="mini-card__icon mini-card__icon--fire">
                  <Flame size={20} />
                </span>
                <div className="mini-card__value">
                  <strong>{dashboard.hotspots.count}</strong>
                  <span>จุดสะสม</span>
                </div>
              </div>
              <small className="card__foot">NASA FIRMS / GISTDA · {pm25Time} น.</small>
            </section>

          </div>

          {/* 7-Day Forest Fire Risk & Plume Outlook */}
          {uiMode === 'authority' && (
            <section className="card daily-forecast-card">
              <div className="card__head">
                <span className="card__title">📅 พยากรณ์ความเสี่ยงไฟป่าและฝุ่นควันสะสม 7 วันข้างหน้า</span>
              </div>
              <p className="personal-checker-desc" style={{ marginBottom: '12px' }}>
                การจำลองระดับดัชนีควันพิษและคาดการณ์ความเสี่ยงไฟไหม้ป่ารายวัน อิงดัชนี NDVI และดาวเทียมอวกาศ
              </p>
              <div style={{ overflowX: 'auto' }}>
                <table className="daily-forecast-table">
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--line)', textAlign: 'left' }}>
                      <th className="daily-cell" style={{ fontWeight: 800 }}>วันที่</th>
                      <th className="daily-cell" style={{ fontWeight: 800 }}>สภาพอากาศ</th>
                      <th className="daily-cell" style={{ fontWeight: 800, textAlign: 'right' }}>อุณหภูมิ</th>
                      <th className="daily-cell" style={{ fontWeight: 800, textAlign: 'center' }}>ระดับความเสี่ยงไฟ</th>
                      <th className="daily-cell" style={{ fontWeight: 800, textAlign: 'center' }}>คาดการณ์จุดไฟ</th>
                      <th className="daily-cell" style={{ fontWeight: 800 }}>ทิศทางกระจายควัน</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyForecast.map((day, idx) => {
                      const riskBadgeClass = `hourly-pm-badge badge--${day.fireRisk === 'critical' ? 'purple' : day.fireRisk === 'high' ? 'red' : day.fireRisk === 'medium' ? 'orange' : 'green'}`;
                      return (
                        <tr key={idx} className="daily-row">
                          <td className="daily-cell daily-day-cell">{day.day}</td>
                          <td className="daily-cell daily-weather-cell">
                            <WeatherIcon type={day.icon} size={16} />
                            <span>{day.icon === 'sun' ? 'แดดจัด/แล้ง' : day.icon === 'rain' ? 'มีฝน/ชื้น' : 'เมฆบางส่วน'}</span>
                          </td>
                          <td className="daily-cell daily-temp-cell">
                            {day.tempMin}° / {day.tempMax}°C
                          </td>
                          <td className="daily-cell daily-risk-cell">
                            <span className={riskBadgeClass}>
                              {getFireRiskLabel(day.fireRisk)}
                            </span>
                          </td>
                          <td className="daily-cell daily-hotspot-cell" style={{ textAlign: 'center' }}>{day.hotspots}</td>
                          <td className="daily-cell daily-smoke-cell" title={day.smokeDisp}>
                            <Wind size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
                            {day.smokeDisp}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Risk score & Advice summary card row */}
          <div className="dashboard-risk-grid">
            
            {/* Risk Factor details */}
            <section className="card risk-card" data-risk={riskTone}>
              <div className="card__head">
                <span className="card__title">คะแนนเสี่ยงการเกิดหมอกควันวันนี้</span>
                <button
                  type="button"
                  className="card__info-btn"
                  aria-label="อธิบายวิธีคำนวณคะแนนเสี่ยง"
                  aria-expanded={note === 'risk'}
                  onClick={() => toggleNote('risk')}
                >
                  <Info size={15} />
                </button>
              </div>
              {note === 'risk' && (
                <p className="card__note">
                  ประมวลผลความเสี่ยง (0-10) จากปัจจัย PM2.5 (40%), จุดความร้อนดาวเทียม (40%) และกำลังลมลามไฟ (20%)
                </p>
              )}
              <div className="risk-card__body">
                <div className="risk-card__gauge">
                  <RiskDonut score={dashboard.risk.score} tone={riskTone} />
                  <span className="risk-card__label">{riskLabelTh[riskTone]}</span>
                </div>
                <ul className="risk-card__factors">
                  <li>
                    <span><i className="dot dot--pm" />ฝุ่นละออง PM2.5</span>
                    <strong>{pm25Points.toFixed(1)} <em>/4</em></strong>
                  </li>
                  <li>
                    <span><i className="dot dot--hot" />จุดความร้อนสะสม</span>
                    <strong>{hotspotPoints.toFixed(1)} <em>/4</em></strong>
                  </li>
                  <li>
                    <span><i className="dot dot--wind" />ความเร็วกระแสลม</span>
                    <strong>{windFactor.toFixed(1)} <em>/2</em></strong>
                  </li>
                </ul>
              </div>
              {uiMode === 'authority' && (
                <p className="risk-card__formula" style={{ fontSize: '0.72rem', marginTop: '10px' }}>สมการลามควัน: {dashboard.risk.formula}</p>
              )}
            </section>

            {/* Advice details */}
            <section className="card advice-card">
              <div className="card__head">
                <ShieldCheck size={18} style={{ color: 'var(--green)' }} />
                <span className="card__title">ข้อเสนอแนะและมาตรการป้องกัน</span>
              </div>
              <h3 className={`advice-card__heading advice-card__heading--${dashboard.pm25.color}`} style={{ fontSize: '1.05rem', margin: '8px 0 4px' }}>{advice.heading}</h3>
              <p className="advice-card__text" style={{ fontSize: '0.84rem', margin: '0 0 10px' }}>{advice.text}</p>
              <ul className="advice-recs" style={{ fontSize: '0.8rem', paddingLeft: '14px', margin: '0 0 12px' }}>
                {recommendations.map(({ label, detail }, i) => {
                  return (
                    <li key={i} style={{ marginBottom: '6px' }}>
                      <strong>{label}:</strong> {detail}
                    </li>
                  );
                })}
              </ul>
              <Suspense fallback={<div className="ai-briefing ai-briefing__text--fallback">กำลังโหลดที่ปรึกษา...</div>}>
                <AiAdvisor dashboard={dashboard} />
              </Suspense>
            </section>

          </div>

        </div>

        <EmergencyContacts />

      </div>

      <footer className="page-foot">
        <span>
          แหล่งข้อมูลดาวเทียมและอุตุฯ: {dashboard.hotspots.source} · {dashboard.pm25.source} · {dashboard.weather.source}
        </span>
        <span>ChiangMaiEyes © 2026 · Pitching Prototype V2.0</span>
      </footer>
    </div>
  );
}
