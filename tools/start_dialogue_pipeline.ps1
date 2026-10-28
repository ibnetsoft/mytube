$ErrorActionPreference = 'Stop'
$taskPipelineRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskPipelineRoot 'venv/Scripts/python.exe'
$taskWorkerLogs = Join-Path $env:LOCALAPPDATA 'AIRStudio/AIRWorker/logs'
New-Item -ItemType Directory -Force -Path $taskWorkerLogs | Out-Null
# Use the current source renderer; the retired packaged renderer predates timing locks.
Push-Location $taskPipelineRoot
try {
    @'
import json,sys
sys.path.insert(0,'worker')
from worker_config import STATE_DIR
from ipc import submit_command,wait_for_result
p=STATE_DIR/'remote_drive_worker.json'
state=json.loads(p.read_text()) if p.exists() else {}
if state.get('current_job_id') or state.get('current_job'):
    raise SystemExit('A render is active. Wait for completion before switching the renderer.')
result=wait_for_result(submit_command('stop_process',{'name':'remote_drive_worker'}),timeout=15)
if not result.get('success'):
    raise SystemExit('Could not stop the previous renderer: '+str(result.get('error')))
'@ | & $taskPython -
    if ($LASTEXITCODE -ne 0) { throw 'Renderer switch failed' }
    foreach ($taskRole in @('remote_render_source', 'lipsync_video_worker', 'ae_mouth_worker')) {
        $taskScript = Join-Path $taskPipelineRoot "worker/$taskRole.py"
        $taskRunning = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -like "*$taskRole.py*" }
        if ($taskRunning) { continue }
        $taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-u', ('"' + $taskScript + '"')) -WorkingDirectory $taskPipelineRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskWorkerLogs "$taskRole.stdout.log") -RedirectStandardError (Join-Path $taskWorkerLogs "$taskRole.stderr.log")
        Write-Output "$taskRole started: $($taskProcess.Id)"
    }
} finally { Pop-Location }
