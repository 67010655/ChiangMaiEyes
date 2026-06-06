// Mocked pitch-mode data. Replace with live API later.

export type HealthBand = 'green' | 'yellow' | 'orange' | 'red';

export type DistrictMeta = {
  name: string; // English key matching GeoJSON properties.name
  label: string; // Thai short label
  num: number;
  health: number; // 0-100
  hotspots: number;
  forests: number;
};

// Short Thai labels + mocked health scores keyed by GeoJSON English name.
export const DISTRICT_META: DistrictMeta[] = [
  { name: 'MaeAi', label: 'แม่อาย', num: 1, health: 72, hotspots: 2, forests: 41 },
  { name: 'Fang', label: 'ฝาง', num: 2, health: 64, hotspots: 3, forests: 38 },
  { name: 'ChiangDao', label: 'เชียงดาว', num: 3, health: 70, hotspots: 4, forests: 52 },
  { name: 'ChaiPrakarn', label: 'ไชยปราการ', num: 4, health: 61, hotspots: 3, forests: 29 },
  { name: 'WiangHaeng', label: 'เวียงแหง', num: 5, health: 58, hotspots: 5, forests: 33 },
  { name: 'MaeTaeng', label: 'แม่แตง', num: 6, health: 66, hotspots: 4, forests: 47 },
  { name: 'Phrao', label: 'พร้าว', num: 7, health: 33, hotspots: 9, forests: 26 },
  { name: 'SanSai', label: 'สันทราย', num: 8, health: 74, hotspots: 1, forests: 18 },
  { name: 'DoiSaket', label: 'ดอยสะเก็ด', num: 9, health: 69, hotspots: 2, forests: 31 },
  { name: 'Samoeng', label: 'สะเมิง', num: 10, health: 55, hotspots: 6, forests: 44 },
  { name: 'HangDong', label: 'หางดง', num: 11, health: 71, hotspots: 1, forests: 22 },
  { name: 'Saraphi', label: 'สารภี', num: 12, health: 76, hotspots: 0, forests: 12 },
  { name: 'SanKamphaeng', label: 'สันป่าตอง', num: 13, health: 67, hotspots: 2, forests: 24 },
  { name: 'Hot', label: 'ฮอด', num: 14, health: 49, hotspots: 7, forests: 39 },
  { name: 'ChomThong', label: 'จอมทอง', num: 15, health: 24, hotspots: 11, forests: 35 },
  { name: 'Omkoi', label: 'อมก๋อย', num: 16, health: 31, hotspots: 10, forests: 58 },
  { name: 'MaeChaem', label: 'แม่แจ่ม', num: 17, health: 35, hotspots: 8, forests: 103 },
  { name: 'MaeRim', label: 'แม่ริม', num: 18, health: 73, hotspots: 1, forests: 19 },
  { name: 'MaeWang', label: 'แม่วาง', num: 19, health: 60, hotspots: 4, forests: 27 },
  { name: 'MuangChiangMai', label: 'เมือง', num: 20, health: 78, hotspots: 0, forests: 8 },
  { name: 'SanPaTong', label: 'สันป่าตอง', num: 21, health: 68, hotspots: 2, forests: 21 },
  { name: 'DoiTao', label: 'ดอยเต่า', num: 22, health: 47, hotspots: 6, forests: 28 },
  { name: 'K.DoiLo', label: 'ดอยหล่อ', num: 23, health: 63, hotspots: 3, forests: 16 },
  { name: 'K.MaeOn', label: 'แม่ออน', num: 24, health: 64, hotspots: 3, forests: 23 },
];

export function healthBand(score: number): HealthBand {
  if (score >= 76) return 'green';
  if (score >= 41) return 'yellow';
  if (score >= 21) return 'orange';
  return 'red';
}

export const BAND_FILL: Record<HealthBand, string> = {
  green: '#4f7a4a',
  yellow: '#c9bf63',
  orange: '#d99a4e',
  red: '#c2603f',
};

export const BAND_FILL_SOFT: Record<HealthBand, string> = {
  green: '#6f9a63',
  yellow: '#d8cf78',
  orange: '#e3ad66',
  red: '#d27a57',
};

export type LeagueRow = {
  rank: number;
  village: string;
  district: string;
  score: number;
  tags: string[];
};

export const LEAGUE: LeagueRow[] = [
  { rank: 1, village: 'บ้านกองลมใหม่', district: 'อ.แม่อาย', score: 92, tags: ['ลาดตระเวน', 'แนวกันไฟ', 'ลดเชื้อเพลิง'] },
  { rank: 2, village: 'บ้านค้อกลาง', district: 'อ.พร้าว', score: 88, tags: ['ลาดตระเวน', 'แนวกันไฟ', 'ประชุมชุมชน'] },
  { rank: 3, village: 'บ้านแม่ทา', district: 'อ.แม่ออน', score: 84, tags: ['ลาดตระเวน', 'ลดเชื้อเพลิง', 'ปลูกป่า'] },
  { rank: 4, village: 'บ้านปาง', district: 'อ.ฝาง', score: 81, tags: ['ลาดตระเวน', 'แนวกันไฟ'] },
  { rank: 5, village: 'บ้านดงสามหมื่น', district: 'อ.แม่แตง', score: 78, tags: ['ลดเชื้อเพลิง', 'ประชุมชุมชน'] },
];

export const PROVINCE_STATS = [
  { label: 'ป่าชุมชนทั้งหมด', value: '573', unit: 'แห่ง' },
  { label: 'พื้นที่ป่าอนุบาล', value: '812,848', unit: 'ไร่' },
  { label: 'ประชากรในพื้นที่', value: '15,693', unit: 'คน' },
  { label: 'ครัวเรือน', value: '16,231', unit: 'ครัวเรือน' },
];

export const WORKFLOW = [
  { step: 1, title: 'Google Form', desc: 'กรอกฟอร์มรับกิจกรรม เลือกกิจกรรม/วันที่/เวลา' },
  { step: 2, title: 'Photo + GPS', desc: 'ถ่ายรูปกิจกรรม ระบบปักหมุดพิกัดอัตโนมัติ' },
  { step: 3, title: 'Activity Proof', desc: 'หลักฐานกิจกรรม ยืนยันข้อมูล ตรวจสอบได้' },
  { step: 4, title: 'Ranking', desc: 'อัปเดตคะแนนรายสัปดาห์ แสดงผลบน League' },
];
