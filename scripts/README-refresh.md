# Hotspot auto-refresh (Thailand egress)

The Royal Forest Department Firemap blocks non-Thai IPs (HTTP 403), so neither
Vercel nor GitHub-hosted runners can fetch it. Hotspots are therefore refreshed
from a machine on a **Thai network** (this PC) and shipped to the deployed app.

Data only updates a few times a day (as VIIRS satellite passes arrive), so the
refresh runs **hourly** but `refresh_snapshot.py` is idempotent — it rewrites
files (→ commit → deploy) **only when the reconciled hotspot set changes**.

## One-time setup

### 1. Vercel: set the backend Root Directory to `backend`
So that `git push` auto-deploys the backend (instead of building the frontend
from the repo root and failing).

- Vercel → project **backend** → **Settings → Build & Deployment**
- **Root Directory** → `backend` → **Save**

(After this, every push that changes backend files deploys the API automatically.
Until then, deploy manually with `vercel --prod` from `backend/`.)

### 2. Register the hourly Scheduled Task
Run once in an **elevated PowerShell** (Run as Administrator):

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\User\Desktop\ChiangMaiEyes\scripts\refresh_and_deploy.ps1"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh' `
  -Action $action -Trigger $trigger -Description 'Hourly RFD/NASA hotspot reconcile + deploy' `
  -RunLevel Highest
```

Verify / run on demand / remove:

```powershell
Start-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh'   # run now
Get-Content scripts\refresh.log -Tail 20                        # see results
Unregister-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh' -Confirm:$false
```

## Notes
- The task needs this PC on and online; if it's off at an update burst, the next
  hourly run catches up.
- `vercel` and `git` must be on PATH and authenticated for the scheduled user.
- The GitHub Action (`.github/workflows/refresh-hotspots.yml`) is dispatch-only:
  GitHub-hosted runners also get 403. It would work only on a self-hosted runner
  attached to a Thai network.
- NASA FIRMS only contributes once a real `NASA_FIRMS_MAP_KEY` is set (free key
  from https://firms.modaps.eosdis.nasa.gov/api/area/). GISTDA's gateway product
  is a global sample; a real GISTDA fire endpoint can be added later.
