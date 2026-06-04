// Physics based fire spread and risk factors for Chiang Mai districts

export interface DistrictPhysics {
  slope_deg: number;
  elevation_m: number;
  forest_type: string;
  fuel_flammability: number;
  history_level: string;
  history_multiplier: number;
}

export const DISTRICT_PHYSICS: Record<string, DistrictPhysics> = {
  'แม่แจ่ม': {
    slope_deg: 28.0,
    elevation_m: 850,
    forest_type: 'ป่าเต็งรังและป่าสนเขา (เชื้อเพลิงใบไม้แห้งและหญ้าหนาแน่น)',
    fuel_flammability: 1.8, // Very High
    history_level: 'เกิดไฟป่าซ้ำซากระดับวิกฤต',
    history_multiplier: 1.5,
  },
  'จอมทอง': {
    slope_deg: 32.0,
    elevation_m: 1450,
    forest_type: 'ป่าดิบเขาและป่าสนเขา (เศษใบสนแห้งสะสมปริมาณมาก)',
    fuel_flammability: 1.5, // High
    history_level: 'เกิดไฟป่าซ้ำซากปานกลาง-สูง',
    history_multiplier: 1.3,
  },
  'เชียงดาว': {
    slope_deg: 35.0,
    elevation_m: 1100,
    forest_type: 'ป่าเบญจพรรณและป่าเต็งรังบนเขาหินปูน (พุ่มไม้แห้งและไผ่ติดไฟง่าย)',
    fuel_flammability: 1.6, // High
    history_level: 'เกิดไฟป่าซ้ำซากสูง',
    history_multiplier: 1.4,
  },
  'แม่ริม': {
    slope_deg: 18.0,
    elevation_m: 420,
    forest_type: 'ป่าเบญจพรรณผลัดใบ (แห้งแล้งสะสมปานกลาง)',
    fuel_flammability: 1.2, // Moderate
    history_level: 'เกิดไฟป่าซ้ำซากต่ำ-ปานกลาง',
    history_multiplier: 1.1,
  },
  'ฝาง': {
    slope_deg: 26.0,
    elevation_m: 920,
    forest_type: 'ป่าสนเขาและป่าดิบเขา (เศษใบไม้แห้งและใบสนสะสมหนาแน่น)',
    fuel_flammability: 1.5, // High
    history_level: 'เกิดไฟป่าซ้ำซากปานกลาง-สูง',
    history_multiplier: 1.3,
  },
  'เมืองเชียงใหม่': {
    slope_deg: 12.0,
    elevation_m: 310,
    forest_type: 'ป่าเบญจพรรณสลับสวนอุทยานและแนวปะทะเขตเมือง',
    fuel_flammability: 0.8, // Low
    history_level: 'เกิดไฟป่าซ้ำซากต่ำ (ได้รับการเฝ้าระวังเข้มงวด)',
    history_multiplier: 1.0,
  },
};

export const DEFAULT_PHYSICS: DistrictPhysics = {
  slope_deg: 20.0,
  elevation_m: 500,
  forest_type: 'ป่าเบญจพรรณและพื้นที่เกษตรกรรมชายขอบป่า',
  fuel_flammability: 1.2, // Moderate
  history_level: 'เกิดไฟป่าซ้ำซากปานกลาง',
  history_multiplier: 1.2,
};

export function getDistrictPhysics(districtName: string | undefined): DistrictPhysics {
  if (!districtName) return DEFAULT_PHYSICS;
  const name = districtName.replace('อำเภอ', '').replace('อ.', '').trim();
  return DISTRICT_PHYSICS[name] || DEFAULT_PHYSICS;
}

// Calculate the Rate of Spread (ROS) multiplier based on wind speed, slope, flammability
export function calculateRateOfSpread(
  slope: number,
  flammability: number,
  historyMult: number,
  windSpeedKmh: number,
  windPushes: boolean
): { rosMultiplier: number; description: string; slopeEffect: number } {
  // Slope effect: fire spreads faster uphill. e^(0.0693 * slope)
  const slopeEffect = Math.exp(0.0693 * slope) / 4.0; // normalized around 20 deg slope (~1.0)
  
  // Wind speed factor
  const windEffect = 1.0 + (windSpeedKmh / 15.0);
  
  // Wind direction multiplier
  const windDirEffect = windPushes ? 1.4 : 0.8;
  
  // Combined ROS multiplier
  const rosMultiplier = flammability * slopeEffect * historyMult * windEffect * windDirEffect;
  
  let description = 'การลามไฟต่ำมาก';
  if (rosMultiplier >= 3.0) {
    description = 'การลามไฟรวดเร็วอย่างวิกฤต (ความชันและแรงลมขับเคลื่อนรุนแรง)';
  } else if (rosMultiplier >= 1.8) {
    description = 'การลามไฟเร็วสูง (พื้นที่แห้งแล้ง/ความลาดชันมีผลส่งเสริม)';
  } else if (rosMultiplier >= 1.0) {
    description = 'การลามไฟระดับปานกลางตามมาตรฐานป่าเบญจพรรณ';
  } else if (rosMultiplier >= 0.5) {
    description = 'การลามไฟช้า (พืชพรรณมีความชื้นหรือพื้นที่ราบ)';
  }
  
  return { rosMultiplier, description, slopeEffect };
}
