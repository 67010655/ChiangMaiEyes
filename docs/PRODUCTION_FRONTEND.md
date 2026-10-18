# ChiangMaiEyes Production Frontend

Production currently boots from `frontend/index.html`.

Community forest totals and boundaries come from
`backend/app/data/community-forests-chiangmai.geojson`, converted from the
shapefile received from RECOFTC. The current file contains 677 polygon
features. `/api/community-forests` returns exactly those features; thaicfnet
can add activity details to a match but cannot add to the count. Run
`python scripts/build_official_layers.py` after changing the GeoJSON to sync
the retained React map data.
Older point and prototype datasets are historical inputs only. They must not
be used to calculate or display the community forest total.

`frontend/src/*` remains in the repo for component experiments, tests, and future migration work, but Vercel does not load `frontend/src/main.tsx` on the live site today.

Rules:
- User-facing production changes must touch `frontend/index.html` or files it fetches from `frontend/public`.
- React `src` changes are not production-visible unless the entry is deliberately migrated.
- Keep static tests around `frontend/index.html` so regressions hit CI/local tests.

Migration path:
1. Move one surface at a time from inline script to React.
2. Preserve API contract and production browser checks.
3. Switch the Vite HTML entry only after parity tests pass.

Release policy (2026-10-18):
- Git pushes and merges do not deploy automatically. Root, frontend and backend
  vercel.json all set git.deploymentEnabled to false.
- Production releases require an explicitly requested manual CLI deployment
  after browser verification of the saved commit. Committing or pushing alone
  does not authorize a release or applying database migrations.
- The frontend and backend Vercel projects were disconnected from the GitHub
  repository with `vercel git disconnect --yes` on 2026-10-18. This prevents
  old branches with older config from triggering automatic deployments too.
  Existing deployments/domains and local `.vercel/project.json` links remain.
  Do not reconnect Git unless automatic deployment is explicitly requested.

Forest coordination (PRODUCT_BRIEF acceptance task 7, 2026-10-18):
- `frontend/public/forest-coordination.js` supplies the first card in hotspot,
  manual-report and private incident details. It uses existing tambon/district
  polygons and the 677-forest API catalog, without filtering neighbors by district.
- Distances are approximate straight lines to forest polygon edges (zero inside).
  A structurally damaged/missing polygon uses its labelled reference point. No
  road/trail distance, jurisdiction assignment, or automatic dispatch is inferred.
- The representative workspace includes fresh points within 5 km where its forest
  is closest across a district boundary, with the neighboring forests shown.
  District at the forest reference point takes precedence over legacy district
  metadata where they disagree. Shared/ambiguous tambon boundaries are labelled.
- `/api/community/contact-status` exposes only a forest id and approval presence.
  `/api/community/forest-contacts` requires a confirmed login plus an admin role or
  at least one currently approved forest membership, and returns only
  currently approved representatives' names and confirmed account email addresses.
  The contact action opens the user's email client; it sends nothing automatically.
  Failed contact lookup is distinct from having no representative. Both paths keep
  government contacts and 1362 available; sign-out clears private card data.
- `scripts/build_forest_agency_contacts.py` regenerates
  `frontend/public/forest-agency-contacts.json` using the publisher's Windows-874
  HTTP charset. Run it with Python 3, optionally `--checked-on YYYY-MM-DD` for a
  reproducible verification date. Only organization, tambon/district, telephone,
  source and checked date fields are retained; no staff or editor names or raw HTML.
  The checked 2026-10-18 snapshot has 26 agencies with published phone numbers
  (24 protection units, the Chiang Mai forest center, and regional office 1).
  Development/fire-promotion units without a published number are omitted.
- Agency selection prefers the same tambon and district, then the same district,
  then one nearest unit by the centroid of its tambon boundary (district boundary
  if its tambon cannot be resolved). The page gives no office coordinates, so the
  fallback is explicitly approximate and does not claim an office-location distance.
  The catalog's `ดอยสะเก็ต` spelling is matched to boundary `ดอยสะเก็ด` without
  overwriting the publisher's stored address. Locality is not a legal assignment.
- Satellite and manual-report popups show detection age and Bangkok time before
  the coordination card. The coordination card owns the single 1362 link.
- Before an explicitly authorized release, apply
  `supabase/migrations/20261018150000_forest_coordination_contacts.sql`, then release
  backend and frontend together. This migration has not been applied to production
  as part of the code change. Until applied, contact lookup falls back to government
  channels without exposing private data. Do not deploy or apply it on Git push.
- The current authoritative 677-record catalog has no forest named Doi Pui.
  The Hang Dong / Doi Pui boundary scenario uses isolated test fixtures only;
  no demonstration forest or coordinator is added to production data.
