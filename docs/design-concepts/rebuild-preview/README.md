# ChiangMaiEyes interactive design preview

Open with a local static server in this folder:

```powershell
python preview_server.py
```

Then open `http://127.0.0.1:8766/`.

Open `http://127.0.0.1:8766/gallery.html` for a visual index of all nine screens. Each card links to a screenshot and its interactive route.

## Screens

- Public situation (`#home`)
- Area map, forest lookup, point detail and time replay (`#map`)
- CCTV viewer with five actual public snapshots, source times, selection, refresh and expansion (`#cameras`)
- Community work, incident report, verification and lessons (`#community`)
- Officer table, real boundary export and camera setup preview (`#officer`)
- Registration, email verification simulation, preferences and email preview (`#account`)
- Illustrated explanations (`#learn`)
- Provenance, missing-data state (`#sources`)
- Terrain screen concept and angled-boundary animation (`#terrain`): illustrative layout, not a working DEM-based 3D renderer

Additional dialogs cover login by email link, camera expansion/setup, forest/point details, report creation and verification, lessons, email confirmation and a PDF report layout concept. CSV export contains real boundary attributes; the PDF dialog does not generate an actual PDF.

The fixed bottom navigation gives direct access to all principal screens.

## Evidence boundaries

`forests.geojson` is an exact copy of `backend/app/data/community-forests-chiangmai.geojson`, containing the 677 real Chiang Mai community-forest polygon records provided through RECOFTC. Names, districts, tambons and areas shown here come from that file. `districts.json` is copied from `frontend/public/chiangmai-districts.json` for geographic context. RECOFTC supplied boundaries only; no activity, fuel, incident or camera records are claimed.

Hotspots, wind, PM, dates, reports and charts are explicitly illustrative fixtures. The map places demonstration points near existing forest records to explore the UI; those are not detected fires. Reports and email form values live only in the current browser page's memory, with no backend writes or email transmissions. Refresh clears them.

CCTV now displays actual public snapshots from AppServ PingRiver: P.1 (Nawarat Bridge), P.67 (Ban Mae Tae), P.75 (Ban Cho Lae), P.92 (Ban Mae Kuet), and P.20 (Ban Ko). These are river-monitoring views, not cameras supplied by RECOFTC or verified community-forest coverage. Per-camera ownership and reuse terms are not yet confirmed. The publisher attributes its hydrology information to irrigation sources; this is kept separate from image ownership.

`preview_server.py` provides a read-only, fixed-source metadata endpoint at `/api/public-cameras`. It fetches the same public station HTML the source site's station selector uses, caches metadata for three minutes, and extracts only an allowlisted station image URL and timestamp from its filename. Browser images load directly from AppServ: no media is downloaded, archived or proxied by the adapter. The browser checks metadata once a minute only while the CCTV route is visible, and only the selected camera image is loaded.

The filename timestamp is explicitly labeled as such. It is not treated as verified capture time: the watermark in the actual image can differ. The interface warns when the filename is older than 30 minutes, shows metadata retrieval time separately, and presents source/image failures without a fabricated replacement image. These are periodic snapshots, not continuous live video.

Resend is the selected future email provider; this prototype simulates verification and preferences and does not call its API. Real integration requires a verified sender domain, backend secret and verified, opted-in recipients.

## Nature asset

`nature.png` was generated with the built-in imagegen tool, then copied into this project. Final prompt: wide, bright editorial landscape of lush northern Thai forest, layered Chiang Mai mountain ridges, small village in a valley, white and forest-green palette, no text, no UI, no flames or smoke. It is an illustrative scene, not geographic evidence or an actual CCTV image. Exact tool prompt is available in the task history.

## Motion

Responsive route transitions, ambient image drift, wind direction flow, point emphasis, dialogs, press/hover/focus feedback and time controls. Global pause and `prefers-reduced-motion` are supported. Time replay represents fixture display only; it does not model continuous fire motion or forecast spread.

The prototype does not replace production `frontend/index.html` and has not been deployed.

## Validation (6 October 2026)

- JavaScript syntax check passed (`node --check app.js`).
- Boundary copy SHA-256 matches the authoritative backend file; 677 polygons rendered in the province view.
- All nine routes rendered at desktop width 1280, tablet width 768 and mobile width 390. No document-level horizontal overflow after repairing the CCTV grid's minimum width. Officer table remains intentionally scrollable within its container.
- Exercised district filtering, a real forest search/selection, layer visibility, zoom/reset, timeline play/pause, camera stale/offline selection, expanded image, community report creation/verification, officer lookup, report layout dialog, login-link flow, registration/confirmation/unsubscribe simulation, lesson switching and missing-data mode.
- Missing-data mode renders no demonstration hotspots and shows no wind direction.
- Browser console contained no error/warning entries in the checked session.
- Screenshots are actual browser captures. Desktop captures include a mixture of full-page and viewport images; use interactive routes to inspect content below the fold.
- Motion pause is tested. CSS supports the operating system's reduced-motion preference; no physical-device or field usability test has been conducted.

## Production integration still required

Public camera snapshots are integrated into this local prototype. Production still needs confirmed ownership/reuse terms, appropriate forest viewpoints and coverage, and a production metadata adapter; authenticated roles and community-area assignments; server-side Resend secrets and verified sending domain; verified recipients, preferences, deduplication and delivery handling; real per-source freshness; report storage and access controls; existing 2D/3D/PDF/CSV and account-feature parity checks. RECOFTC activity/fuel data must remain unavailable until actually received.

## Public-camera source review (6 October 2026)

- [AppServ PingRiver](https://appserv.net/pingriver.php): five station names and public image URLs verified from its actual station-switching interface. All five images loaded in the local preview. No playback tokens, logins or restricted camera endpoints are used.
- [Irrigation hydrology CCTV directory](https://water.rid.go.th/hyd/Report/cctv.html): confirms a public Chiang Mai river-camera context at P.67; this does not establish ownership/reuse terms for every image.
- [DOH northern CCTV list](https://www.highwaytraffic.go.th/DOHMobile/Modules/CCTV2.aspx?group=%E0%B8%A0%E0%B8%B2%E0%B8%84%E0%B9%80%E0%B8%AB%E0%B8%99%E0%B8%B7%E0%B8%AD): Chiang Mai entries included old update indicators; not labeled as current live feeds or added to the viewer.
- [Chiang Mai PAO CCTV page](https://www.chiangmaipao.go.th/all_cctv): public page contained standby/preview placeholders during review; not treated as a working camera source.
- Five parser/failure tests passed: station-origin constraints, filename timezone provenance, missing/invalid timestamps, upstream failure without fabricated images, and disallowed redirects.
- Browser QA passed at desktop 1280 and mobile 390: all five actual images loaded with nonzero natural dimensions, selecting P.92 changed the image and metadata, expanded view showed that camera, refresh returned to its ready state, and no app console errors/warnings or framework overlay were present. Mobile document width matched its viewport. Physical-device behavior and future upstream outages remain unverified.
