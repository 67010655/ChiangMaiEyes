# 15-minute hotspot refresh, run from a Thailand network because RFD blocks many foreign IPs.
#
# The Python refresh reconciles RFD/GISTDA/NASA, refreshes PM2.5/weather, and
# writes refresh_status.json on every successful check. Changed data is committed,
# pushed, and deployed to production so the public API can prove freshness.

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

function Run-BackendProductionDeploy {
  Log 'refresh: deploying backend production'
  cmd.exe /d /c "npx.cmd vercel@latest deploy . --project backend --prod --yes >> ""$log"" 2>>&1"
  if ($LASTEXITCODE -ne 0) {
    throw "vercel backend deploy exited $LASTEXITCODE"
  }
  Log 'refresh: backend production deployed'
}

$dataFiles = @(
  'backend/data/hotspots.json',
  'backend/data/pm25.json',
  'backend/data/weather.json',
  'backend/data/refresh_status.json',
  'frontend/src/data/dashboardSnapshot.json'
)

try {
  Log 'refresh: start'
  Run-PythonRefresh

  $changed = git status --porcelain -- $dataFiles
  if (-not $changed) { Log 'refresh: no data change - done'; exit 0 }

  Log 'refresh: data changed - commit + push'
  git add $dataFiles
  git commit -m 'chore: refresh hotspot snapshot (RFD/NASA reconciliation)'
  git push origin HEAD:codex/production-wind-chip
  Log 'refresh: pushed snapshot branch'
  Run-BackendProductionDeploy
}
catch {
  Log "refresh: ERROR $_"
  exit 1
}
