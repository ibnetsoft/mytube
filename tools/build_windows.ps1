param(
    [string]$Version = "0.1.0",
    [string]$GitHubRepo = "OWNER/REPO",
    [switch]$SkipInstaller,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Spec = Join-Path $Root "packaging\windows\AIRStudio.spec"
$ReleaseDir = Join-Path $Root "release"
$DistDir = Join-Path $Root "dist\AIRStudio"
$StagingRoot = Join-Path $ReleaseDir "staging\AIRStudio"
$StagingApp = Join-Path $StagingRoot "app"
$StagingLauncher = Join-Path $StagingRoot "Launcher"
$ZipPath = Join-Path $ReleaseDir "AIRStudio-$Version-win-x64.zip"
$ManifestPath = Join-Path $ReleaseDir "latest.json"

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Push-Location $Root
try {
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUSERBASE = Join-Path $Root ".pyuserbase"
    New-Item -ItemType Directory -Force -Path $env:PYTHONUSERBASE | Out-Null

    if (-not (Test-Path "venv\Scripts\python.exe")) {
        python -m venv venv
    }

    if (-not $SkipDependencyInstall) {
        & "venv\Scripts\python.exe" -m pip install -r requirements.txt
        & "venv\Scripts\python.exe" -c "import PyInstaller" 2>$null
        if ($LASTEXITCODE -ne 0) {
            & "venv\Scripts\python.exe" -m pip install pyinstaller
        }
    }

    & "venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean $Spec

    if (-not (Test-Path $DistDir)) {
        throw "PyInstaller output not found: $DistDir"
    }

    if (Test-Path $StagingRoot) {
        Remove-Item -LiteralPath $StagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $StagingApp | Out-Null
    New-Item -ItemType Directory -Force -Path $StagingLauncher | Out-Null

    Copy-Item -Path (Join-Path $DistDir "*") -Destination $StagingApp -Recurse -Force

    & "venv\Scripts\python.exe" -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name AIRLauncher `
        --distpath $StagingLauncher `
        --workpath (Join-Path $Root "build\AIRLauncher") `
        (Join-Path $Root "packaging\windows\launcher\AIRLauncher.py")

    & "venv\Scripts\python.exe" -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name AIRUpdater `
        --distpath $StagingLauncher `
        --workpath (Join-Path $Root "build\AIRUpdater") `
        (Join-Path $Root "packaging\windows\launcher\AIRUpdater.py")

    @{
        manifest_url = "https://github.com/$GitHubRepo/releases/latest/download/latest.json"
    } | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $StagingLauncher "update_config.json") -Encoding UTF8

    @{
        version = $Version
    } | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $StagingRoot "current.json") -Encoding UTF8

    if (Test-Path $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    Compress-Archive -Path (Join-Path $StagingRoot "*") -DestinationPath $ZipPath -Force

    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash.ToLowerInvariant()
    $Manifest = [ordered]@{
        version = $Version
        channel = "stable"
        mandatory = $false
        installer_url = "https://github.com/$GitHubRepo/releases/download/v$Version/AIRStudioSetup-$Version.exe"
        portable_url = "https://github.com/$GitHubRepo/releases/download/v$Version/AIRStudio-$Version-win-x64.zip"
        sha256 = $Hash
        notes = "AIR Studio Windows build $Version"
    }
    $Manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $ManifestPath -Encoding UTF8

    if (-not $SkipInstaller) {
        $Inno = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if ($null -eq $Inno) {
            Write-Warning "ISCC.exe was not found. Install Inno Setup or rerun with -SkipInstaller."
        } else {
            $env:PICADILLY_VERSION = $Version
            & $Inno.Source (Join-Path $Root "packaging\windows\AIRStudio.iss")
        }
    }

    Write-Host "Build complete:"
    Write-Host "  $ZipPath"
    Write-Host "  $ManifestPath"
    Write-Host "  $StagingRoot"
} finally {
    Pop-Location
}
