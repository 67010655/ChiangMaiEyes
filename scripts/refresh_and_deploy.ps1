# 30-minute hotspot refresh — run from a Thailand network (RFD blocks foreign IPs).
#
# Fetches + reconciles RFD/GISTDA/NASA and, ONLY when the reconciled hotspot
# set actually changed, commits the snapshot and pushes. The push triggers
# Vercel's git auto-deploy of the backend.
#
# PREREQUISITE: set the backend Vercel project's Root Directory to "backend"
# (Settings -> Build & Deployment), otherwise the push won't deploy the backend.
#
# The refresh script is idempotent, so most hourly runs do nothing.
# Register as an hourly Scheduled Task — see scripts/README-refresh.md.

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\User\Desktop\ChiangMaiEyes'
Set-Location $repo

$log = Join-Path $repo 'scripts\refresh.log'
function Log($m) {
  $line = "$([DateTime]::Now.ToString('s'))  $m"
  Write-Output $line
  $line | Out-File -FilePath $log -Append -Encoding utf8
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
  'frontend/src/data/dashboardSnapshot.json'
)

try {
  Log 'refresh: start'
  Run-PythonRefresh

  # The refresh only rewrites files when the reconciled hotspots changed.
  $changed = git status --porcelain -- $dataFiles
  if (-not $changed) { Log 'refresh: no data change — done'; exit 0 }

  Log 'refresh: data changed — commit + push'
  git add $dataFiles
  git commit -m 'chore: refresh hotspot snapshot (RFD/NASA reconciliation)'
  git push
  Log 'refresh: pushed (Vercel will auto-deploy)'
}
catch {
  Log "refresh: ERROR $_"
  exit 1
}
