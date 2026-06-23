import type { HotspotResponse } from './types';

function csvCell(value: unknown): string {
  const s = value === null || value === undefined ? '' : String(value);
  // Quote when the cell contains a comma, quote, or newline (RFC 4180).
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Download the current hotspots as a CSV so authorities can drop the data
 * straight into their own reports/meetings. BOM-prefixed so Excel reads Thai
 * (UTF-8) correctly.
 */
export function downloadHotspotsCsv(hotspots: HotspotResponse): void {
  const headers = [
    'id',
    'latitude',
    'longitude',
    'district',
    'subdistrict',
    'landuse_type',
    'landuse_name',
    'satellite',
    'confidence',
    'source',
    'detected_at',
  ];

  const rows = hotspots.items.map((h) =>
    [
      h.id,
      h.latitude,
      h.longitude,
      h.district,
      h.subdistrict ?? '',
      h.landuse_type ?? '',
      h.landuse_name ?? '',
      h.satellite ?? '',
      h.confidence,
      h.source,
      h.detected_at,
    ]
      .map(csvCell)
      .join(','),
  );

  const csv = '﻿' + [headers.join(','), ...rows].join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const stamp = (hotspots.latest_update || new Date().toISOString()).slice(0, 10);

  const a = document.createElement('a');
  a.href = url;
  a.download = `chiangmai-hotspots-${stamp}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
