$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = (Get-Command python -ErrorAction Stop).Source
& $taskPython (Join-Path $taskRoot 'worker/install.py') --role script
if ($LASTEXITCODE -ne 0) { throw 'Script worker installation failed.' }
