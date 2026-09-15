$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskUrl = 'http://127.0.0.1:3003'
try {
    $taskHealth = Invoke-RestMethod "$taskUrl/health" -TimeoutSec 2
    if ($taskHealth.service -eq 'codex-local-console') {
        Write-Output "Already running: $taskUrl"
        exit 0
    }
    throw 'Port 3003 is occupied by another service.'
} catch {
    if (Get-NetTCPConnection -LocalPort 3003 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 3003 is occupied; no process was stopped.'
    }
}
$taskPython = (Get-Command python -ErrorAction Stop).Source
$taskOutput = Join-Path $taskRoot 'output/codex-local-console'
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList '-m','worker.codex_local_console' -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskOutput 'server.stdout.log') -RedirectStandardError (Join-Path $taskOutput 'server.stderr.log')
for ($taskTry = 0; $taskTry -lt 20; $taskTry++) {
    Start-Sleep -Milliseconds 500
    if ($taskProcess.HasExited) { throw 'Codex console exited. Check output/codex-local-console/server.stderr.log.' }
    try {
        $taskHealth = Invoke-RestMethod "$taskUrl/health" -TimeoutSec 2
        if ($taskHealth.service -eq 'codex-local-console') { Write-Output "Codex local console started: $taskUrl (PID $($taskProcess.Id))"; exit 0 }
    } catch { }
}
throw 'Startup not confirmed. Check the local log before trying again.'
