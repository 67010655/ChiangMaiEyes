export type MapSelection = {
  eyebrow: string;
  title: string;
  detail: string;
  mapUrl?: string;
  sourceUrl?: string;
  sourceLabel?: string;
  imageKey?: string;
  imageLabel?: string;
  stats?: { label: string; value: string; tone?: 'good' | 'watch' | 'risk' }[];
  lat?: number;
  lng?: number;
};

export function getDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export const initialSelection: MapSelection = {
  eyebrow: 'ขอบเขตจังหวัด',
  title: 'เชียงใหม่',
  detail:
    'จังหวัดขนาดใหญ่ทางภาคเหนือ พื้นที่ประมาณ 20,107 ตร.กม. ใช้ดู PM2.5 จุดความร้อน และทิศทางลมแบบโฟกัสเฉพาะเชียงใหม่',
  imageKey: 'province',
  imageLabel: 'Chiang Mai province',
  stats: [
    { label: 'พื้นที่', value: '20,107 ตร.กม.' },
    { label: 'อำเภอ', value: '24 อำเภอ' },
  ],
};
