# Hotspot auto-refresh (Thailand egress)

The Royal Forest Department Firemap blocks non-Thai IPs (HTTP 403), so neither
Vercel nor GitHub-hosted runners can fetch it. Hotspots are therefore refreshed
from a machine on a **Thai network** (this PC) and shipped to the deployed app.

Data updates several times a day (VIIRS + MODIS satellite passes), so the
refresh runs **every 30 minutes** but `refresh_snapshot.py` is idempotent — it
rewrites files (→ commit → deploy) **only when the reconciled hotspot set changes**.
Most runs do nothing; the shorter interval just means we pick up new passes sooner.

## One-time setup

### 1. Vercel: set the backend Root Directory to `backend`
So that `git push` auto-deploys the backend (instead of building the frontend
from the repo root and failing).

- Vercel → project **backend** → **Settings → Build & Deployment**
- **Root Directory** → `backend` → **Save**

(After this, every push that changes backend files deploys the API automatically.
Until then, deploy manually with `vercel --prod` from `backend/`.)

### 2. Register the 30-minute Scheduled Task
Run once in an **elevated PowerShell** (Run as Administrator):

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\User\Desktop\ChiangMaiEyes\scripts\refresh_and_deploy.ps1"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh' `
  -Action $action -Trigger $trigger -Description '30-min RFD/NASA/MODIS hotspot reconcile + deploy' `
  -RunLevel Highest
```

Verify / run on demand / remove:

```powershell
Start-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh'   # run now
Get-Content scripts\refresh.log -Tail 20                        # see results
Unregister-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh' -Confirm:$false
```

### 3. (Optional) Heartbeat monitoring via healthchecks.io

Know immediately when the PC goes offline or the refresh breaks.

1. Sign up free at https://healthchecks.io → create a new check
2. Set **Period** = 1 hour, **Grace** = 1 hour (alerts if no ping for 2 hours)
3. Copy the ping URL (e.g. `https://hc-ping.com/xxxxxxxx-xxxx-...`)
4. Add to `backend/.env`:
   ```
   HEALTHCHECK_URL=https://hc-ping.com/your-uuid-here
   ```
5. The refresh script pings the URL automatically on each successful run.

### 4. (Optional) Email proximity alerts

Lets users pin a location on the map, log in with a magic-link email, and get
emailed when a new hotspot appears inside their chosen radius (10/25/50 km).

**Requires:**
1. A Supabase project (free tier) — already provisioned at
   `https://zskizogquupkneubcayc.supabase.co` with the `alert_subscriptions` /
   `alert_notifications` tables and Row Level Security set up.
2. A free [Resend](https://resend.com) account (3,000 emails/month free).

**Setup:**
1. Frontend `.env` (or Vercel env): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
   (the **publishable**/anon key — safe to expose client-side).
2. `backend/.env` (refresh worker only — never the Vercel backend):
   ```
   SUPABASE_URL=https://zskizogquupkneubcayc.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=<service_role key from Supabase → Settings → API>
   RESEND_API_KEY=<your Resend API key>
   RESEND_FROM_EMAIL=ChiangMaiEyes <onboarding@resend.dev>
   ```
   ⚠️ The **service_role** key bypasses Row Level Security — keep it only in the
   refresh worker's `.env`, never in the frontend or Vercel backend env vars.
3. That's it — `refresh_snapshot.py` checks subscriptions against today's
   reconciled hotspots after every run and emails matches via Resend. Sent
   matches are recorded in `alert_notifications` so the same fire isn't emailed
   twice.

If any of the three keys (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`RESEND_API_KEY`) are missing, alert checking is skipped silently — the rest of
the refresh behaves exactly as before.

## Notes
- The task needs this PC on and online; if it's off at an update burst, the next
  30-minute run catches up.
- `vercel` and `git` must be on PATH and authenticated for the scheduled user.
- The GitHub Action (`.github/workflows/refresh-hotspots.yml`) is dispatch-only:
  GitHub-hosted runners also get 403. It would work only on a self-hosted runner
  attached to a Thai network.
- NASA FIRMS keys are free from https://firms.modaps.eosdis.nasa.gov/api/area/.
  The same key covers both VIIRS and MODIS.
- MODIS (Terra + Aqua) passes at different times than VIIRS, so adding it
  reduces the gap between usable satellite overpasses.
