# Himawari + VIIRS: engineering probe for ChiangMaiEyes

Verified 18 October 2026. Research only; no app/UI/deployment changes, signup, payment, provider contact or third-party API key. This is a concrete working data adapter, not a claim that prediction skill has improved.

## Result

**Public, machine-readable JAXA Himawari-9 fire detections for the 2026 Chiang Mai burning season are accessible without credentials.** The official monitor's current JavaScript loads L2WLF010 GeoJSON. We reproduced those requests, retained raw files and checksums, normalized the observations and matched some against strictly earlier VIIRS observations. This is preferable for this experiment to inventing a detector from raw infrared radiance.

Example actually downloaded:

- [24 March 2026 06:00 UTC](https://www.eorc.jaxa.jp/ptree/map2/himawari/L2_WLF/010/2026/03/24/H09_20260324_0600.json)
- [24 March 2026 06:10 UTC](https://www.eorc.jaxa.jp/ptree/map2/himawari/L2_WLF/010/2026/03/24/H09_20260324_0610.json)
- [24 March 2024 06:00 UTC](https://www.eorc.jaxa.jp/ptree/map2/himawari/L2_WLF/010/2024/03/24/H09_20240324_0600.json)
- [24 March 2025 06:00 UTC](https://www.eorc.jaxa.jp/ptree/map2/himawari/L2_WLF/010/2025/03/24/H09_20250324_0600.json)

The URL pattern is evidenced by [official monitor source](https://www.eorc.jaxa.jp/ptree/js/himawariMonitor_v3r5.js), function `setWlfLayer`, rather than guessed private endpoints. It is a public web data layer, **not a documented stable API or service-level guarantee**. The source code was saved only as provenance, not incorporated as our code.

## Actual bounded probe

Four dates selected to span January–April: 2026-01-15, 2026-02-15, 2026-03-24, 2026-04-02, at 00/03/06/09/12/15/18/21 UTC, plus March24 06:10/06:20/06:30 UTC. Window 98–99.8°E, 17.2–20.2°N, **a Chiang Mai-area rectangle, not the province polygon**.

| Verified quantity | Result |
|---|---:|
| Requested / HTTP200 frames | 35 / 35 |
| Download size | 3,625,154 bytes |
| Detection rows within rectangle | 365 |
| Rows with reliability3/5 and volcano0 | 326 |
| Those corroborated by eligible earlier VIIRS within4km | 44 |

The match uses nominal/high VIIRS detections from the preceding24h, excluding the last3h as an explicit VIIRS availability-delay assumption. This is **positive corroboration only**, not precision, sensitivity, speed advantage, an independent truth set or proof of operational availability. Different sensors sample different times/footprints; unmatched rows cannot be called false alarms.

2024 and2025 March24 06:00 frames separately returned HTTP200, 693/1,902 full-disk features and6/2 rows in the rectangle (5/2 quality eligible). These are access checks, not seasonal completeness checks.

## Source interpretation and caveats

JAXA documents L2 wildfire output every10minutes, approximately2km at nadir, with reliability and fire-level classifications. The geographic spacing in its CSV documentation is0.02°, which is not a20m or375m fire boundary. Latitude/longitude represent the reported grid centre. [JAXA product guide](https://www.eorc.jaxa.jp/ptree/userguide.html), [L2WLF format](https://www.eorc.jaxa.jp/ptree/documents/README_Himawari_L2WLF.txt).

The downloaded GeoJSON contains `RELIABILITY`, `FRP`, `LEVEL`, `VOLCANO`, and Point coordinates. It does **not** contain per-pixel acquisition or processing timestamps, a cloud mask, coverage QA, the CSV's hot-centre ID or detailed FRP QF. The adapter preserves what exists and does not manufacture the missing fields. Nominal UTC observation time comes from the provider filename; it is not exact pixel scan time.

The CSV README labels FRP asW/m² and defines cluster power using pixel area, whereas other web layers display aggregated power inMW. The GeoJSON has no unit declaration or area. Consequently **`frp_web_raw` is retained with `frp_web_unit='unverified'` and is excluded from quantitative power features**. Do not copy its values into VIIRS MW fields or calibrate emission rates with it.

`publication_time_utc` remains null. HTTP `Last-Modified` is saved; example2024/25 values were about43/45minutes after nominal acquisition, but that is not proof of first availability. A retrospective model can use a documented fixed delay (e.g.3h), clearly identified as a scenario; it cannot claim a strict as-issued operational backtest. `first_retrieved_at_utc` records today's retrieval, never backdated availability.

**No detection is not a negative observation.** Cloud, weak/subpixel fire, missing frame, algorithm omissions and actual no fire are not distinguishable from this detections-only layer. Repeated positive observations can support a fire-active feature; absent observations must not assert extinguishment. NASA also treats current geostationary fire outputs as provisional because commission and omission errors are material. [NASA geostationary guidance](https://wiki.earthdata.nasa.gov/spaces/FIRMS/blog/2024/06/25/377718041/Geostationary%2BActive%2BFire%2BDetection%2BData%2Bin%2BFIRMS).

JAXA's FAQ describes removal of older non-hourly **web images**, with complete products via FTP. That must not be generalized to vectorJSON: **all three tested March2026 06:10/20/30 vector frames were still accessible**. Completeness at10minute cadence across a whole season remains unverified. [FAQ](https://www.eorc.jaxa.jp/ptree/faq.html).

## Reusable code and output contract

`backend/scripts/probe_himawari_fire_sources.py` uses the Python standard library, two download workers, bounded4MB frames, retries and source receipts. No added packages or core-engine edits.

```python
from datetime import datetime, timezone
from pathlib import Path
from probe_himawari_fire_sources import fetch_frame

receipt, detections = fetch_frame(
    datetime(2026, 3, 24, 6, tzinfo=timezone.utc),
    Path('output/fire-engineering-20261018/himawari-probe'),
    bbox=(98, 17.2, 99.8, 20.2),
)
```

Receipt: status, HTTP status, URL, raw SHA256, bytes, nominal observation time, today's retrieval time, optional server Last-Modified, publication time unknown, coverage semantics. Missing response is `missing_or_error`, never a fabricated empty successful observation.

Detection: id, latitude, longitude, observation time, publication null, retrieval time, source identifier/URL/hash, reliability, eligible flag, level, volcano, rawFRP/unitunknown and nominal grid spacing. `quality_eligible` means provider reliability3/5 and non-volcanic; it is an experimental inclusion rule, not independent validation.

Reproduce the probe in PowerShell:

```powershell
backend/.venv-research/Scripts/python -X utf8 backend/scripts/probe_himawari_fire_sources.py --dates 2026-01-15 2026-02-15 2026-03-24 2026-04-02 --hours 0 3 6 9 12 15 18 21 --probe-ten-minute-retention
```

Outputs under `output/fire-engineering-20261018/himawari-probe/`: `raw/` data+receipts, `frame-manifest.json`, `events.json`, `past-viirs-corroboration.json`, `summary.json`, `older-year-probe.json`, `verification.json`. Verification passed source parsing, unknown publication/units, empty observation handling, exclusion of future VIIRS and rejection of timezone-naive timestamps.

## Integration that can now be tested

For each frozen forecast origin, sample only earlier nominal frames after the declared delay; record requested and successful frames separately. Derive distance to the nearest recent reliable Himawari detection and the number/age of positive revisits near VIIRS. KeepVIIRS375m andHimawari2km identities separate; repeated2km centroids must not become independent fine-resolution fires. CompareVIIRS-only withVIIRS+Himawari on the same selected cases and area budget. Do not tune this addition using test-year outcomes.

## Other routes checked

- FIRMS' map includes Himawari geostationary products, but its **documented Area CSV source list currently contains Landsat/MODIS/VIIRS, not Himawari**. Therefore an existing FIRMS MAP_KEY does not establish a supported Himawari AreaCSV route. We did not use a website's hidden key. [Area API](https://firms.modaps.eosdis.nasa.gov/api/area/).
- JAXA's documented full historical L2/L3 wildfire CSV archive is supplied throughP-TreeFTP with account registration. This was not required for the public web-layer probe and no registration was performed. [Geo-product directory specification](https://www.eorc.jaxa.jp/ptree/documents/README_HimawariGeo_en.txt), [FAQ](https://www.eorc.jaxa.jp/ptree/faq.html).
- NOAA's publicAWSHimawari archive is rawAHIL1b, not ready fire CSV; no radiance files were downloaded because the actual fire-product route above worked. [Open-data registry](https://registry.opendata.aws/noaa-himawari/).
- Credit JAXA'sHimawari wildfire research product andJMA source observations. Our present use is offline research. Before public/commercial distribution, follow the current provider's product-specific terms; access without a key is not a blanket new license. [JAXA research-data terms](https://earth.jaxa.jp/en/data/policy/), [P-Tree use FAQ](https://www.eorc.jaxa.jp/ptree/faq.html).
