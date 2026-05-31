export function riskLabel(score: number): 'Low' | 'Medium' | 'High' {
  if (score <= 3) return 'Low';
  if (score <= 6) return 'Medium';
  return 'High';
}

export function riskPercent(score: number): number {
  return Math.max(0, Math.min(score, 10)) * 10;
}
