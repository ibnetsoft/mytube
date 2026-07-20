#Requires -Version 5.1
<#
.SYNOPSIS
    AIR Studio Windows build pipeline (AIR-0216).

.DESCRIPTION
    Builds PyInstaller bundle, Launcher/Updater binaries, and optional Inno Setup
    installer.  Produces a standardised release/ directory:

        release/
          AIRStudio-{version}-win-x64.zip           portable archive
          AIRStudio-{version}-win-x64.zip.sha256     SHA256 sidecar
          AIRStudioSetup-{version}.exe               Inno Setup installer
          AIRStudioSetup-{version}.exe.sha256        SHA256 sidecar
          latest.json                                update manifest
          latest.json.sha256                         SHA256 sidecar

.PARAMETER Version
    Semantic version string (default: "0.1.0").  Pass "auto" to read from
    packaging/windows/VERSION.txt.

.PARAMETER Build
    Integer build / task ID.  Pass 0 (default) to auto-increment from
    packaging/windows/build_counter.txt.

.PARAMETER GitHubRepo
    GitHub repository in OWNER/REPO format (default: ibnetsoft/AIR-releases).
    Releases are published to a separate public repo so the source repo can
    stay private; this only affects the URLs embedded in latest.json.

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
    [string]$GitHubRepo = "ibnetsoft/AIR-releases",
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
$StagingApp      = Join-Path $StagingRoot "app"
$StagingLauncher = Join-Path $StagingRoot "Launcher"

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
$ManifestPath     = Join-Path $ReleaseDir "latest.json"

Write-Host ""
Write-Host "=== AIR Studio Windows Build ==="
Write-Host "  Version : $Version"
Write-Host "  Build   : $Build"
Write-Host "  Channel : $Channel"
Write-Host "  Repo    : $GitHubRepo"
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
    New-Item -ItemType Directory -Force -Path $StagingApp      | Out-Null
    New-Item -ItemType Directory -Force -Path $StagingLauncher | Out-Null

    Copy-Item -Path (Join-Path $DistDir "*") -Destination $StagingApp -Recurse -Force

    # ---- .env (public config + SMTP credentials for packaged app) ----
    # [AIR-0225B] SUPABASE_SERVICE_ROLE_KEY must NEVER be written here. This key
    # bypasses Postgres RLS entirely; embedding it in a package that ships to
    # every end user's PC turned every public GitHub release into a full-database
    # credential leak (see worknote/AIR-0225B-stage0-service-role-removal-investigation.md).
    # The desktop app must only ever carry the public Supabase URL (safe to expose
    # by design - NEXT_PUBLIC_*) plus a user JWT obtained at login time. Any feature
    # still requiring privileged Supabase access must be proxied through auth-web.
    $EnvSupabaseUrl = $env:NEXT_PUBLIC_SUPABASE_URL
    $EnvLines = @()
    if ($EnvSupabaseUrl) {
        $EnvLines += "NEXT_PUBLIC_SUPABASE_URL=$EnvSupabaseUrl"
    } else {
        Write-Warning "NEXT_PUBLIC_SUPABASE_URL not set - packaged app will ship without a Supabase URL."
    }

    # SMTP (회원가입 이메일 인증코드 발송용). AIR-0225: previously missing here
    # entirely, so send_verify_code() silently failed on every packaged build
    # (services/email_service.py returns False when SMTP_USER/SMTP_PASS are
    # unset - no crash, no visible error, just "발송에 실패했습니다").
    $EnvSmtpHost = $env:SMTP_HOST
    $EnvSmtpPort = $env:SMTP_PORT
    $EnvSmtpUser = $env:SMTP_USER
    $EnvSmtpPass = $env:SMTP_PASS
    $EnvSmtpFrom = $env:SMTP_FROM
    if ($EnvSmtpUser -and $EnvSmtpPass) {
        if ($EnvSmtpHost) { $EnvLines += "SMTP_HOST=$EnvSmtpHost" }
        if ($EnvSmtpPort) { $EnvLines += "SMTP_PORT=$EnvSmtpPort" }
        $EnvLines += "SMTP_USER=$EnvSmtpUser"
        $EnvLines += "SMTP_PASS=$EnvSmtpPass"
        if ($EnvSmtpFrom) { $EnvLines += "SMTP_FROM=$EnvSmtpFrom" }
    } else {
        Write-Warning "SMTP_USER / SMTP_PASS not set - packaged app will ship without email-sending credentials (signup verification codes will fail to send)."
    }

    if ($EnvLines.Count -gt 0) {
        Write-Host "Writing packaged .env with $($EnvLines.Count) credential line(s)..."
        $EnvLines -join "`n" | Set-Content -Path (Join-Path $StagingApp ".env") -Encoding UTF8 -NoNewline
    }

    # ---- PyInstaller: AIRLauncher ----
    Write-Host "Building AIRLauncher.exe..."
    & "venv\Scripts\python.exe" -m PyInstaller `
        --noconfirm --clean --onefile --noconsole `
        --name AIRLauncher `
        --distpath $StagingLauncher `
        --workpath (Join-Path $Root "build\AIRLauncher") `
        (Join-Path $Root "packaging\windows\launcher\AIRLauncher.py")

    # ---- PyInstaller: AIRUpdater ----
    Write-Host "Building AIRUpdater.exe..."
    & "venv\Scripts\python.exe" -m PyInstaller `
        --noconfirm --clean --onefile --noconsole `
        --name AIRUpdater `
        --distpath $StagingLauncher `
        --workpath (Join-Path $Root "build\AIRUpdater") `
        (Join-Path $Root "packaging\windows\launcher\AIRUpdater.py")

    # ---- update_config.json ----
    @{
        manifest_url = "https://github.com/$GitHubRepo/releases/latest/download/latest.json"
    } | ConvertTo-Json -Depth 3 | Set-Content `
        -Path (Join-Path $StagingLauncher "update_config.json") -Encoding UTF8

    # ---- Canonical version record ----
    $InstalledAt  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $VersionRecord = [ordered]@{
        version      = $Version
        installed_at = $InstalledAt
        build        = $Build
    }
    $VersionRecordJson = $VersionRecord | ConvertTo-Json -Depth 3

    # NOTE: `Set-Content -Encoding UTF8` in Windows PowerShell 5.1 always emits a
    # UTF-8 BOM (there is no utf8NoBOM encoding until PS Core 6+, and this script
    # targets 5.1 - see #Requires above). config.py reads this file with plain
    # "utf-8", so a BOM makes json.load() throw and APP_VERSION silently ends up
    # "" - the sidebar version display then never renders. Write without a BOM
    # explicitly via .NET instead of Set-Content.
    $Utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText((Join-Path $StagingRoot "current.json"), $VersionRecordJson, $Utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $StagingApp  "version.json"), $VersionRecordJson, $Utf8NoBom)

    # ---- Portable ZIP ----
    Write-Host "Creating portable ZIP: $ZipName"
    if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
    Compress-Archive -Path (Join-Path $StagingRoot "*") -DestinationPath $ZipPath -Force

    # ---- latest.json + ZIP SHA256 ----
    Write-Host "Computing ZIP SHA256..."
    $ZipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash.ToLowerInvariant()

    $Manifest = [ordered]@{
        version       = $Version
        build         = $Build
        channel       = $Channel
        mandatory     = $false
        installer_url = "https://github.com/$GitHubRepo/releases/download/v$Version/$InstallerName"
        portable_url  = "https://github.com/$GitHubRepo/releases/download/v$Version/$ZipName"
        sha256        = $ZipHash
        notes         = "AIR Studio v$Version (build $Build, channel $Channel)"
    }
    $Manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $ManifestPath -Encoding UTF8

    # ---- SHA256 sidecar files ----
    Write-Host ""
    Write-Host "--- Release artifacts ---"
    Write-Host "ZIP      : $ZipPath"
    Write-Sha256Sidecar -FilePath $ZipPath | Out-Null

    Write-Host "Manifest : $ManifestPath"
    Write-Sha256Sidecar -FilePath $ManifestPath | Out-Null

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
    Write-Host "  $ManifestPath"
    Write-Host "  $ManifestPath.sha256"
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
