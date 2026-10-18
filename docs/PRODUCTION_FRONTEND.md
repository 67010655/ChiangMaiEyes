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
