# 5-minute hotspot refresh, run from a Thailand network because RFD blocks many foreign IPs.
#
# The Python refresh reconciles RFD/GISTDA/NASA, refreshes PM2.5/weather, and
# writes refresh_status.json on every successful check. Changed data is committed
# and pushed. Production reads the latest JSON from GitHub raw, so this task must
# not deploy every 5 minutes and burn through the Vercel daily deployment quota.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$branch = 'codex/production-wind-chip'

$log = Join-Path $repo 'scripts\refresh.log'
function Log($m) {
  $line = "$([DateTime]::Now.ToString('s'))  $m"
  Write-Output $line
  $line | Out-File -FilePath $log -Append -Encoding utf8
}

function Sync-WorkerCheckout {
  if ($repo -notlike '*ChiangMaiEyes-refresh-worker*') {
    Log 'refresh: skip worker self-sync outside refresh-worker checkout'
    return
  }

  $dirty = git status --porcelain
  if ($dirty) {
    throw 'worker checkout is dirty before refresh; refusing to overwrite local changes'
  }

  Log 'refresh: syncing worker checkout'
  git fetch origin $branch
  if ($LASTEXITCODE -ne 0) {
    throw "git fetch exited $LASTEXITCODE"
  }

  git reset --hard "origin/$branch"
  if ($LASTEXITCODE -ne 0) {
    throw "git reset exited $LASTEXITCODE"
  }
}

function Run-PythonRefresh {
  $previousPythonEncoding = $env:PYTHONIOENCODING
  try {
    $env:PYTHONIOENCODING = 'utf-8'
    cmd.exe /d /c "python backend\scripts\refresh_snapshot.py >> ""$log"" 2>>&1"
    if ($LASTEXITCODE -ne 0) {
      throw "refresh_snapshot.py exited $LASTEXITCODE"
    }
  }
  finally {
    if ($null -eq $previousPythonEncoding) {
      Remove-Item Env:\PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    else {
      $env:PYTHONIOENCODING = $previousPythonEncoding
    }
  }
}

$dataFiles = @(
  'backend/data/hotspots.json',
  'backend/data/pm25.json',
  'backend/data/weather.json',
  'backend/data/refresh_status.json',
  'backend/data/satellite_layers.json',
  'frontend/src/data/dashboardSnapshot.json'
)

try {
  Log 'refresh: start'
  Sync-WorkerCheckout
  Run-PythonRefresh

  $changed = git status --porcelain -- $dataFiles
  if (-not $changed) { Log 'refresh: no data change - done'; exit 0 }

  Log 'refresh: data changed - commit + push'
  git add $dataFiles
  git commit -m 'chore: refresh hotspot snapshot (RFD/NASA reconciliation)'
  git push origin "HEAD:$branch"
  Log 'refresh: pushed snapshot branch - production will read remote snapshot'
}
catch {
  Log "refresh: ERROR $_"
  exit 1
}
