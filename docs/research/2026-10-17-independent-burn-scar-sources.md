# Independent burn-scar references for Chiang Mai, January–April 2026

Checked 17 October 2026. Research only; no production changes or credentials used.

## Actionable result

Use **TamRoyPao B4 Sentinel-2 20 m weekly burn detections** for a separately observed spatial-agreement diagnostic. Anonymous GeoTIFF downloads and HTTP range reads work. This reference does **not** establish six-hour fire progression or verified fire absence. Keep the existing future-hotspot evaluation separate.

### Product meaning and access

The provider describes B4 as two integer bands: band 1 counts burn-scar detections; band 2 counts satellite images/acquisitions within the filename's interval. It does not identify band 2 as cloud-free observations. Therefore, `band2 > 0 && band1 == 0` means **no burn detected despite recorded acquisition(s)**, not confirmed unburned ground. A zero acquisition count is insufficient evidence. Filename dates bound the composite interval; they are not exact ignition/arrival times. [Provider product descriptions](https://tamroypao.hii.or.th/)

The same page explicitly says forest detection has not received formal accuracy assessment and tree canopy can cause errors. Treat agreement and disagreement as diagnostic evidence; do not label pixel precision/recall against this product as true fire accuracy. Its daily B1 product is described on the [map's about panel](https://tamroypao.hii.or.th/tamroypao_map/map.jsp), but no public B1 folder was listed in the [product directory](https://tamroypao.hii.or.th/product/).

The public product page invites downloading and reuse with attribution; no explicit machine-readable license was found, and `product/readme.txt` was empty. Preserve attribution to TamRoyPao / HII / Kasetsart University and retrieval metadata. Do not invent a CC license. [Provider](https://tamroypao.hii.or.th/), [readme](https://tamroypao.hii.or.th/product/readme.txt)

### Verified direct example

`https://tamroypao.hii.or.th/product/B4/2026/03/BURNSCAR_47QMA_20M_20260319_20260325_B4.tif`

Downloaded HTTP 200, 3,297,993 bytes. Range request returned HTTP 206. Rasterio inspection found EPSG:32647; 5,490 × 5,490 cells; 20 × 20 m; two int16 bands; LZW; no explicit nodata value. WGS84 bounds approximately `[98.049591,17.997827,99.092727,18.992522]`. In this file band 1 contained 0/1/2 and band 2 contained 0/1/2. These are file inspection results, not provider accuracy claims. Download retained at `output/burn-reference-research/sample-47QMA-20260319-20260325.tif`.

### Chiang Mai bounding-box tile candidates

Small range reads verified these twelve tiles intersect the requested broad bbox `[98.0,17.2,99.5,20.2]`: `47QLV`, `47QLA`, `47QLB`, `47QLC`, `47QMV`, `47QMA`, `47QMB`, `47QMC`, `47QNV`, `47QNA`, `47QNB`, `47QNC`. They cover the bbox, not just province polygons; clip the actual province and incident windows. Exact inspected bounds and sample URLs are in `output/burn-reference-research/tile-metadata.json`.

Anonymous directory listings were checked:

| Listing | Candidate files present | Composite starts and ends |
|---|---:|---|
| [January](https://tamroypao.hii.or.th/product/B4/2026/01/) | 57 | Jan 1–7, 8–14, 15–21, 22–28, Jan 29–Feb 4 |
| [February](https://tamroypao.hii.or.th/product/B4/2026/02/) | 46 | Feb 5–11, 12–18, 19–25, Feb 26–Mar 4 |
| [March](https://tamroypao.hii.or.th/product/B4/2026/03/) | 34 | Mar 5–11, 12–18, 19–25, Mar 26–Apr 1 |
| [April](https://tamroypao.hii.or.th/product/B4/2026/04/) | 48 | Apr 2–8, 9–15, 16–22, 23–29, Apr 30–May 6 |

This is **185 listed tile-period files**, not all 216 possible tile-period combinations. Do not fabricate missing files. The listing's directory month corresponds to the interval start. For an April 1 prediction the March directory is relevant. Full exact URLs, listing SHA-256 and status codes are in `output/burn-reference-research/b4-2026-jan-apr-manifest.json`. The [merged 2026 directory](https://tamroypao.hii.or.th/product/MB4/2026/) also lists weekly national mosaics, but per-tile data is more economical.

## Alternative references and why they do not unblock anonymous six-hour validation

**GISTDA** provides latest burn polygons and a query for burn dates within the past 365 days. Official metadata says API-key registration is required; the example endpoint is `https://api-gateway.gistda.or.th/api/2.0/resources/gi-service/v1.0/disasters/burnt-area-latest?lat={latitude}&lon={longitude}&api_key=[YOUR-API-KEY]`. It is potentially relevant to Jan–Apr 2026, but not an anonymous data source established by this investigation. Its catalog does not establish subdaily perimeter timing. [Official catalog](https://opendata.gistda.or.th/dataset/disasters-04)

**Copernicus CLMS burnt area v4** is global, daily, 300 m, with burn fraction, classification probability, day of burn and large-fraction probability. Official documentation describes free use for any purpose. Day-of-burn is daily, not a six-hour arrival timestamp. [Official data documentation](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/clms/bio-geophysical-parameters/vegetation/burnt-area/ba_global_300m_daily_v4.html)

The anonymous STAC query below returned a real March 29, 2026 item, `c_gls_BA300-NRT_202603290000_GLOBE_S3_V4.0.1_nc`. Its published timestamp was March 30 15:51:03 UTC, and its metadata was updated May 6. The 232 MB NetCDF download explicitly declares OIDC/S3 authentication. A small unauthenticated HTTPS range request returned HTTP 401 `Token not found`. Therefore public catalog discovery works; anonymous raster access was **not** established. Item metadata is saved at `output/burn-reference-research/clms-stac-sample.json`.

`https://stac.dataspace.copernicus.eu/v1/collections/clms_ba_global_300m_daily_v4_nc/items?limit=1&datetime=2026-03-29T00:00:00Z/2026-03-29T23:59:59Z`

[Exact official STAC item](https://stac.dataspace.copernicus.eu/v1/collections/clms_ba_global_300m_daily_v4_nc/items/c_gls_BA300-NRT_202603290000_GLOBE_S3_V4.0.1_nc)

**GWIS near-real-time perimeters must not be presented as independent validation of VIIRS hotspot forecasts.** The owner says its NRT perimeter delineation uses combined MODIS and VIIRS thermal anomalies. Historical GlobFire products have different provenance, so check product identity rather than treating every GWIS polygon equally. [GWIS technical description](https://gwis.jrc.ec.europa.eu/about-gwis/technical-background/burnt-areas)

## Implementation recommendation

1. Read only listed B4 tiles intersecting an incident's fixed evaluation extent, retain band 2 and source dates.
2. Compare the deployed prediction and an equal-area isotropic baseline with the same weekly scar reference, fixed extent and raster alignment. Report predicted area, intersection, reference area and acquisition coverage.
3. Title these results **weekly observed scar agreement**, explicitly recording the six-hour versus seven-day mismatch. A scar can predate the seed, occur after the six-hour forecast, persist over several periods, or be obscured by clouds/canopy.
4. Do not tune fuel/spread parameters against all these weekly maps and then report the same maps as held-out validation. Keep dates/incidents separated.
5. Actual subdaily perimeter validation still needs dated independent image pairs or field perimeter observations. The public sources inspected here do not supply that evidence.
