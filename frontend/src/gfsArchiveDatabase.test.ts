import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { afterAll, beforeAll, expect, test } from 'vitest';

let db: PGlite;
const raw = readFileSync(new URL('../../backend/tests/fixtures/gfs_pbl_20261012_06_f000.grib2', import.meta.url));
const hash = createHash('sha256').update(raw).digest('hex');
const sample = () => ({ sha256: hash, run_at: '2026-10-12T06:00:00Z', valid_at: '2026-10-12T06:00:00Z',
  retrieved_at: '2026-10-12T08:00:00Z', forecast_hour: 0, bbox: '98.0086,17.2732,99.5730,20.1474',
  cells: [{ latitude: 18.75, longitude: 99, pbl_height_m: 21, ventilation_rate_m2_s: 0 }],
  field_metadata: [{}, {}, {}, {}], status: 'available', measurement_kind: 'model',
  publisher: 'NOAA NCEP', product: 'GFS 0.25° PBL',
  source_url: 'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?file=test', reference_cell: { ventilation_rate_m2_s: 0 } });

beforeAll(async () => {
  db = new PGlite();
  await db.exec('create role anon; create role authenticated; create role service_role;');
  await db.exec(readFileSync(new URL('../../supabase/migrations/20261013003000_gfs_model_archive.sql', import.meta.url), 'utf8'));
}, 30000);
afterAll(async () => db?.close());

test('raw hash is checked, identical files preserve their first record and database evidence time', async () => {
  const first = await db.query<{ result: any }>('select public.cme_gfs_ingest($1,$2) result', [JSON.stringify(sample()), raw.toString('base64')]);
  expect(first.rows[0].result.inserted).toBe(1);
  expect(new Date(first.rows[0].result.first_stored_at).getTime()).toBeGreaterThan(new Date('2026-10-12T08:00:00Z').getTime());
  const changedMetadata = { ...sample(), retrieved_at: '2026-10-12T09:00:00Z' };
  const second = await db.query<{ result: any }>('select public.cme_gfs_ingest($1,$2) result', [JSON.stringify(changedMetadata), raw.toString('base64')]);
  expect(second.rows[0].result.inserted).toBe(0);
  expect(second.rows[0].result.first_stored_at).toBe(first.rows[0].result.first_stored_at);
  const saved = await db.query<{ hash: string; retrieved_at: string }>('select encode(sha256(grib),\'hex\') hash,payload->>\'retrieved_at\' retrieved_at from public.cme_gfs_frames');
  expect(saved.rows[0]).toEqual({ hash, retrieved_at: sample().retrieved_at });
  await expect(db.query('select public.cme_gfs_ingest($1,$2)', [JSON.stringify({ ...sample(), sha256: '0'.repeat(64) }), raw.toString('base64')])).rejects.toThrow();
});

test('past cutoff excludes files that had not been stored yet; raw bytes stay out of public reader payloads', async () => {
  const past = await db.query<{ result: any }>('select public.cme_gfs_read($1,$2,0,20) result', ['2026-10-11T00:00:00Z', '2026-10-12T08:00:00Z']);
  expect(past.rows[0].result.total).toBe(0);
  const now = new Date(Date.now() + 1000).toISOString();
  const read = await db.query<{ result: any }>('select public.cme_gfs_read($1,$2,0,20) result', ['2026-10-11T00:00:00Z', now]);
  expect(read.rows[0].result.total).toBe(1);
  expect(read.rows[0].result.frames[0].reference_cell.ventilation_rate_m2_s).toBe(0);
  expect(read.rows[0].result.frames[0].grib).toBeUndefined();
  const hidden = await db.query<{ result: any }>('select public.cme_gfs_frame($1,$2) result', [hash, '2026-10-12T08:00:00Z']);
  expect(hidden.rows[0].result).toBeNull();
});

test('only service code can ingest/read tables and scientific RPCs; malformed windows fail', async () => {
  const result = await db.query<{ allowed: boolean }>(`select has_table_privilege('anon','public.cme_gfs_frames','SELECT') or
    has_table_privilege('authenticated','public.cme_gfs_frames','INSERT') or
    has_function_privilege('anon','public.cme_gfs_ingest(jsonb,text)','EXECUTE') or
    has_function_privilege('authenticated','public.cme_gfs_read(timestamptz,timestamptz,integer,integer)','EXECUTE') allowed`);
  expect(result.rows[0].allowed).toBe(false);
  await expect(db.query('select public.cme_gfs_read(now(),now()-interval \'1 day\',0,20)')).rejects.toThrow();
});
