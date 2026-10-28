$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$managerPath = Join-Path $workspace 'worker\local_media_supervisor.py'
$pattern = [regex]::Escape($managerPath)
$running = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match $pattern
})
if ($running.Count) { Write-Output 'Local media supervisor already running'; exit 0 }
$logDirectory = Join-Path $env:LOCALAPPDATA 'AIRStudio\AIRWorker\logs\local-media'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$pythonPath = (Get-Command python.exe).Source
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','-u',('"' + $managerPath + '"'),'--port','3004') `
    -WorkingDirectory $workspace -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDirectory 'supervisor.stdout.log') `
    -RedirectStandardError (Join-Path $logDirectory 'supervisor.stderr.log')
Write-Output "Local media supervisor started: $($process.Id)"
