# Hotspot Auto-Refresh (Thailand Egress)

The Royal Forest Department Firemap blocks many non-Thai IPs, so Vercel and
GitHub-hosted runners cannot be trusted to fetch the full RFD dataset directly.
Hotspots are refreshed from a machine on a Thai network, then shipped to the
deployed app as a snapshot.

The worker runs every 15 minutes. Satellite detections may update less often
than that, but the 15-minute cadence lets the app detect a stalled worker
quickly. `refresh_snapshot.py` writes `refresh_status.json` on every successful
check, even when the hotspot count is unchanged.

## One-Time Setup

### 1. Vercel: set backend Root Directory to `backend`

Set this in the Vercel backend project:

- Project: `backend`
- Settings -> Build & Deployment
- Root Directory -> `backend`

### 2. Register the 15-minute Scheduled Task

Run once in PowerShell:

```powershell
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\User\Desktop\ChiangMaiEyes\scripts\refresh_and_deploy.ps1"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh' `
  -Action $action -Trigger $trigger -Description '15-minute RFD/GISTDA/NASA hotspot reconcile + deploy'
```

Verify, run on demand, or remove:

```powershell
Get-ScheduledTaskInfo -TaskName 'ChiangMaiEyes hotspot refresh'
Start-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh'
Get-Content scripts\refresh.log -Tail 40
Unregister-ScheduledTask -TaskName 'ChiangMaiEyes hotspot refresh' -Confirm:$false
```

## Runtime Contract

- This PC must be powered on and online.
- `git`, `npx`, and Vercel authentication must work for the scheduled user.
- The frontend treats `refresh_age_minutes > 30` as a warning.
- The frontend treats `refresh_status != ok` or `refresh_age_minutes > 60` as stale.
- PM2.5 and weather still refresh live from the backend on user visits.
