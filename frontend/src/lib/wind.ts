export function directionName(degrees: number) {
  const directions = ['เหนือ', 'ตะวันออกเฉียงเหนือ', 'ตะวันออก', 'ตะวันออกเฉียงใต้', 'ใต้', 'ตะวันตกเฉียงใต้', 'ตะวันตก', 'ตะวันตกเฉียงเหนือ'];
  const idx = Math.floor(((degrees + 22.5) % 360) / 45);
  return directions[idx];
}

export function windDestinationName(sourceDegrees: number) {
  return directionName((sourceDegrees + 180) % 360);
}
