$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = (Get-Command python -ErrorAction Stop).Source
$taskUrl = 'http://127.0.0.1:3004'
try {
    $taskHealth = Invoke-RestMethod "$taskUrl/health" -TimeoutSec 2
    if ($taskHealth.service -eq 'air-local-media') { Write-Output "Already running: $taskUrl"; exit 0 }
} catch { }
if (Get-NetTCPConnection -LocalPort 3004 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 3004 is occupied; no process was stopped.' }
$taskLogs = Join-Path $taskRoot 'output/local-media'
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList '-u','-m','worker.launch','--role','local' -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLogs 'manager.stdout.log') -RedirectStandardError (Join-Path $taskLogs 'manager.stderr.log')
for ($taskTry=0; $taskTry -lt 20; $taskTry++) {
    Start-Sleep -Milliseconds 500
    if ($taskProcess.HasExited) { throw 'Local media manager exited. Check output/local-media/manager.stderr.log.' }
    try {
        $taskHealth=Invoke-RestMethod "$taskUrl/health" -TimeoutSec 2
        if ($taskHealth.service -eq 'air-local-media') { Write-Output "Local media manager started: $taskUrl (PID $($taskProcess.Id))"; exit 0 }
    } catch { }
}
throw 'Startup not confirmed; inspect the manager log before restarting.'
