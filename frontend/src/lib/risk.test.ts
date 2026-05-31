import { describe, expect, it } from 'vitest';
import { riskLabel, riskPercent } from './risk';

describe('risk helpers', () => {
  it('maps scores to transparent categories', () => {
    expect(riskLabel(3)).toBe('Low');
    expect(riskLabel(4)).toBe('Medium');
    expect(riskLabel(7)).toBe('High');
  });

  it('clamps risk percent for display', () => {
    expect(riskPercent(-2)).toBe(0);
    expect(riskPercent(5)).toBe(50);
    expect(riskPercent(12)).toBe(100);
  });
});
