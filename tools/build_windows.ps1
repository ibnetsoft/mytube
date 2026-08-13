#Requires -Version 5.1
<#
.SYNOPSIS
    AIR Studio Windows build pipeline (AIR-0216).

.DESCRIPTION
    Builds the PyInstaller bundle and optional Inno Setup installer. Produces a
    standardised release/ directory:

        release/
          AIRStudio-{version}-win-x64.zip           portable archive
          AIRStudio-{version}-win-x64.zip.sha256     SHA256 sidecar
          AIRStudioSetup-{version}.exe               Inno Setup installer
          AIRStudioSetup-{version}.exe.sha256        SHA256 sidecar

.PARAMETER Version
    Semantic version string (default: "0.1.0").  Pass "auto" to read from
    packaging/windows/VERSION.txt.

.PARAMETER Build
    Integer build / task ID.  Pass 0 (default) to auto-increment from
    packaging/windows/build_counter.txt.

.PARAMETER Channel
    Release channel: "stable" | "beta" | "dev" (default: stable).

.PARAMETER SkipInstaller
    Skip Inno Setup step even if ISCC.exe is available.

.PARAMETER SkipDependencyInstall
    Skip pip install steps (faster if dependencies are already installed).

.EXAMPLE
    # Auto-increment build, specific version
    .\build_windows.ps1 -Version 1.0.0

    # Explicit build number, beta channel
    .\build_windows.ps1 -Version 1.0.0 -Build 220 -Channel beta

    # Skip installer (portable ZIP only)
    .\build_windows.ps1 -Version 1.0.0 -SkipInstaller
#>
param(
    [string]$Version = "0.1.0",
    [int]$Build = 0,
    [ValidateSet("stable","beta","dev")]
    [string]$Channel = "stable",
    [switch]$SkipInstaller,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$Root            = Resolve-Path (Join-Path $PSScriptRoot "..")
$Spec            = Join-Path $Root "packaging\windows\AIRStudio.spec"
$CounterFile     = Join-Path $Root "packaging\windows\build_counter.txt"
$ReleaseDir      = Join-Path $Root "release"
$DistDir         = Join-Path $Root "dist\AIRStudio"
$StagingRoot     = Join-Path $ReleaseDir "staging\AIRStudio"
$StagingApp      = $StagingRoot

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

# ---------------------------------------------------------------------------
# Build number — auto-increment from build_counter.txt
# ---------------------------------------------------------------------------
function Get-NextBuildNumber {
    param([string]$CounterPath)
    if (Test-Path $CounterPath) {
        $current = [int](Get-Content $CounterPath -Raw).Trim()
    } else {
        $current = 0
    }
    $next = $current + 1
    Set-Content -Path $CounterPath -Value $next -NoNewline -Encoding UTF8
    return $next
}

if ($Build -eq 0) {
    $Build = Get-NextBuildNumber -CounterPath $CounterFile
    Write-Host "Auto-incremented build number: $Build"
} else {
    # If an explicit build number is provided, update the counter if it's higher
    if (Test-Path $CounterFile) {
        $stored = [int](Get-Content $CounterFile -Raw).Trim()
        if ($Build -gt $stored) {
            Set-Content -Path $CounterFile -Value $Build -NoNewline -Encoding UTF8
        }
    } else {
        Set-Content -Path $CounterFile -Value $Build -NoNewline -Encoding UTF8
    }
    Write-Host "Using explicit build number: $Build"
}

# Artifact paths (final names)
$ZipName          = "AIRStudio-$Version-win-x64.zip"
$InstallerName    = "AIRStudioSetup-$Version.exe"
$ZipPath          = Join-Path $ReleaseDir $ZipName
$InstallerPath    = Join-Path $ReleaseDir $InstallerName

Write-Host ""
Write-Host "=== AIR Studio Windows Build ==="
Write-Host "  Version : $Version"
Write-Host "  Build   : $Build"
Write-Host "  Channel : $Channel"
Write-Host ""

# ---------------------------------------------------------------------------
# SHA256 helper
# ---------------------------------------------------------------------------
function Write-Sha256Sidecar {
    param([string]$FilePath)
    if (-not (Test-Path $FilePath)) { return }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $FilePath).Hash.ToLowerInvariant()
    $sidecar = "$FilePath.sha256"
    # Format: "<hash>  <filename>" (standard sha256sum format)
    $fileName = Split-Path $FilePath -Leaf
    Set-Content -Path $sidecar -Value "$hash  $fileName" -Encoding UTF8
    Write-Host "  SHA256 : $hash"
    Write-Host "  Sidecar: $sidecar"
    return $hash
}

# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------
Push-Location $Root
try {
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUSERBASE   = Join-Path $Root ".pyuserbase"
    New-Item -ItemType Directory -Force -Path $env:PYTHONUSERBASE | Out-Null

    # ---- Python / venv setup ----
    if (-not (Test-Path "venv\Scripts\python.exe")) {
        Write-Host "Creating virtualenv..."
        python -m venv venv
    }

    if (-not $SkipDependencyInstall) {
        Write-Host "Installing dependencies..."
        & "venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
        & "venv\Scripts\python.exe" -c "import PyInstaller" 2>$null
        if ($LASTEXITCODE -ne 0) {
            & "venv\Scripts\python.exe" -m pip install --quiet pyinstaller
        }
    }

    # ---- PyInstaller: main app bundle ----
    Write-Host "Building AIRStudio bundle..."
    & "venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean $Spec
    if (-not (Test-Path $DistDir)) {
        throw "PyInstaller output not found: $DistDir"
    }

    # ---- Staging layout ----
    if (Test-Path $StagingRoot) {
        Remove-Item -LiteralPath $StagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $StagingApp | Out-Null

    Copy-Item -Path (Join-Path $DistDir "*") -Destination $StagingApp -Recurse -Force

    # Keep the installed app's displayed version aligned with the release
    # artifact. config.py reads this file before falling back to version.py.
    # Write release metadata without a BOM. python-dotenv otherwise sees the
    # first .env key as a different name on Windows PowerShell builds.
    $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $VersionRecord = [ordered]@{
        version = $Version
        build = $Build
        channel = $Channel
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $StagingApp "version.json"),
        ($VersionRecord | ConvertTo-Json -Compress),
        $Utf8NoBom
    )

    # ---- .env (public configuration only) ----
    # Public desktop packages must never contain credentials. The Supabase URL is
    # intentionally public; all privileged access and email delivery stay server-side.
    $EnvSupabaseUrl = $env:NEXT_PUBLIC_SUPABASE_URL
    if (-not $EnvSupabaseUrl) {
        $RootEnvPath = Join-Path $Root ".env"
        if (Test-Path $RootEnvPath) {
            $PublicUrlLine = Get-Content -LiteralPath $RootEnvPath | Where-Object {
                $_ -match '^\s*NEXT_PUBLIC_SUPABASE_URL\s*='
            } | Select-Object -First 1
            if ($PublicUrlLine -match '^\s*NEXT_PUBLIC_SUPABASE_URL\s*=\s*(.*)$') {
                $EnvSupabaseUrl = $Matches[1].Trim().Trim('"').Trim("'")
            }
        }
    }
    $EnvLines = @()
    if ($EnvSupabaseUrl) {
        $EnvLines += "NEXT_PUBLIC_SUPABASE_URL=$EnvSupabaseUrl"
    } else {
        Write-Warning "NEXT_PUBLIC_SUPABASE_URL not set - packaged app will ship without a Supabase URL."
    }

    if ($EnvLines.Count -gt 0) {
        Write-Host "Writing packaged public .env with $($EnvLines.Count) line(s)..."
        [System.IO.File]::WriteAllText(
            (Join-Path $StagingApp ".env"),
            ($EnvLines -join "`n"),
            $Utf8NoBom
        )
    }

    # ---- Portable ZIP ----
    Write-Host "Creating portable ZIP: $ZipName"
    if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    Compress-Archive -Path (Join-Path $StagingRoot "*") -DestinationPath $ZipPath -Force

    # ---- SHA256 sidecar files ----
    Write-Host ""
    Write-Host "--- Release artifacts ---"
    Write-Host "ZIP      : $ZipPath"
    Write-Sha256Sidecar -FilePath $ZipPath | Out-Null

    # ---- Inno Setup installer ----
    $InstallerBuilt = $false
    if (-not $SkipInstaller) {
        $Inno = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if ($null -eq $Inno) {
            Write-Warning "ISCC.exe not found — skipping installer. Install Inno Setup or use -SkipInstaller."
        } else {
            Write-Host "Building installer: $InstallerName"
            $env:AIR_VERSION      = $Version
            $env:AIR_RELEASE_DIR  = $ReleaseDir
            & $Inno.Source (Join-Path $Root "packaging\windows\AIRStudio.iss")
            if (Test-Path $InstallerPath) {
                $InstallerBuilt = $true
                Write-Host "Installer: $InstallerPath"
                Write-Sha256Sidecar -FilePath $InstallerPath | Out-Null
            } else {
                Write-Warning "Installer output not found at $InstallerPath"
            }
        }
    }

    # ---- Build summary ----
    Write-Host ""
    Write-Host "=== Build complete ==="
    Write-Host "  Version  : $Version"
    Write-Host "  Build    : $Build"
    Write-Host "  Channel  : $Channel"
    Write-Host ""
    Write-Host "Release artifacts:"
    Write-Host "  $ZipPath"
    Write-Host "  $ZipPath.sha256"
    if ($InstallerBuilt) {
        Write-Host "  $InstallerPath"
        Write-Host "  $InstallerPath.sha256"
    }
    Write-Host ""
    Write-Host "To publish to GitHub Releases:"
    if ($InstallerBuilt) {
        Write-Host "  .\tools\release_github.ps1 -Version $Version -Build $Build"
    } else {
        Write-Host "  .\tools\release_github.ps1 -Version $Version -Build $Build -SkipInstaller"
    }
    Write-Host ""

} finally {
    Pop-Location
}
