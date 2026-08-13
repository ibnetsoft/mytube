#Requires -Version 5.1
<#
.SYNOPSIS
    Publishes a built AIR Studio release to GitHub Releases (AIR-0216).

.DESCRIPTION
    Uses the GitHub CLI (gh) to:
      1. Create a GitHub Release tag v{Version}
      2. Upload the desktop ZIP, installer, and SHA256 files

    Prerequisites:
      - GitHub CLI installed: https://cli.github.com
      - Authenticated: gh auth login
      - Release artifacts built with build_windows.ps1

.PARAMETER Version
    Semantic version of the release (e.g. "1.0.0").

.PARAMETER Build
    Build / task ID (informational, included in release notes).

.PARAMETER GitHubRepo
    GitHub repository in OWNER/REPO format (default: ibnetsoft/AIR-releases).
    This is the separate public releases-only repo; gh must be authenticated
    with a token that has Contents:write on it (source repo can stay private).

.PARAMETER Channel
    Release channel label (default: stable).

.PARAMETER Draft
    Create the release as a draft (requires manual publish on GitHub).

.PARAMETER Prerelease
    Mark the release as a pre-release.

.PARAMETER SkipInstaller
    Do not attempt to upload installer .exe (use when -SkipInstaller was passed to build_windows.ps1).

.PARAMETER NotesFile
    Path to a Markdown file whose content becomes the release body.
    Defaults to release/RELEASE_NOTES.md if it exists; otherwise auto-generated.

.EXAMPLE
    # Normal stable release
    .\tools\release_github.ps1 -Version 1.0.0 -Build 216

    # Draft pre-release, beta channel
    .\tools\release_github.ps1 -Version 1.1.0-beta -Build 217 -Channel beta -Draft -Prerelease

    # Re-upload after build (useful if gh upload failed)
    .\tools\release_github.ps1 -Version 1.0.0 -Build 216 -SkipInstaller
#>
param(
    [Parameter(Mandatory)]
    [string]$Version,

    [int]$Build = 0,

    [string]$GitHubRepo = "ibnetsoft/AIR-releases",

    [ValidateSet("stable","beta","dev")]
    [string]$Channel = "stable",

    [switch]$Draft,
    [switch]$Prerelease,
    [switch]$SkipInstaller,

    [string]$NotesFile = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root        = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseDir  = Join-Path $Root "release"
$Tag         = "v$Version"
$ZipName     = "AIRStudio-$Version-win-x64.zip"
$InstallerName = "AIRStudioSetup-$Version.exe"

# ---------------------------------------------------------------------------
# Verify gh CLI is available and authenticated
# ---------------------------------------------------------------------------
function Assert-GhCli {
    if (-not (Get-Command "gh" -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI (gh) not found. Install from https://cli.github.com and run 'gh auth login'."
    }
    $status = & gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "gh is not authenticated. Run 'gh auth login' first."
    }
}

# ---------------------------------------------------------------------------
# Verify expected artifacts exist
# ---------------------------------------------------------------------------
function Assert-Artifact {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path $Path)) {
        throw "Expected artifact not found: $Path ($Label). Run build_windows.ps1 first."
    }
    Write-Host "  [OK] $Path"
}

# ---------------------------------------------------------------------------
# Generate release notes if no notes file provided
# ---------------------------------------------------------------------------
function Get-ReleaseNotes {
    param([string]$Path)
    if ($Path -and (Test-Path $Path)) {
        return Get-Content $Path -Raw -Encoding UTF8
    }
    $defaultNotes = Join-Path $ReleaseDir "RELEASE_NOTES.md"
    if (Test-Path $defaultNotes) {
        return Get-Content $defaultNotes -Raw -Encoding UTF8
    }
    # Auto-generate minimal notes
    return @"
## AIR Studio v$Version (build $Build)

Channel: **$Channel**

### Artifacts
- ``AIRStudio-${Version}-win-x64.zip`` — portable archive (no installer required)
- ``AIRStudioSetup-${Version}.exe`` — Windows installer

SHA256 checksums are published alongside each artifact.
"@
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Assert-GhCli

Write-Host ""
Write-Host "=== GitHub Release: $Tag ==="
Write-Host "  Repo     : $GitHubRepo"
Write-Host "  Channel  : $Channel"
Write-Host "  Draft    : $($Draft.IsPresent)"
Write-Host "  Prerelease: $($Prerelease.IsPresent)"
Write-Host ""

# Verify artifacts
Write-Host "Verifying release artifacts..."
$ZipPath          = Join-Path $ReleaseDir $ZipName
$ZipSha256Path    = "$ZipPath.sha256"
$InstallerPath    = Join-Path $ReleaseDir $InstallerName
$InstallerSha256  = "$InstallerPath.sha256"

Assert-Artifact $ZipPath         "portable ZIP"
Assert-Artifact $ZipSha256Path   "ZIP SHA256 sidecar"

if (-not $SkipInstaller) {
    Assert-Artifact $InstallerPath    "Inno Setup installer"
    Assert-Artifact $InstallerSha256  "installer SHA256 sidecar"
}

# Build file list for upload
$UploadFiles = @(
    $ZipPath,
    $ZipSha256Path
)
if (-not $SkipInstaller) {
    $UploadFiles += $InstallerPath
    $UploadFiles += $InstallerSha256
}

# Release notes
$Notes = Get-ReleaseNotes -Path $NotesFile

# Write notes to temp file (gh create expects a file path)
$NotesTmp = Join-Path $env:TEMP "air_release_notes_$Version.md"
Set-Content -Path $NotesTmp -Value $Notes -Encoding UTF8

# Build gh release create arguments
$CreateArgs = @(
    "release", "create", $Tag,
    "--repo", $GitHubRepo,
    "--title", "AIR Studio v$Version",
    "--notes-file", $NotesTmp
)
if ($Draft)      { $CreateArgs += "--draft" }
if ($Prerelease) { $CreateArgs += "--prerelease" }

# Check if release already exists. `gh release view` exits 1 when the tag is
# absent, which is the normal create-release path and must not be promoted to a
# terminating PowerShell native-command error.
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$existingRelease = & gh release view $Tag --repo $GitHubRepo 2>$null
$releaseExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousErrorActionPreference
if ($releaseExists) {
    Write-Warning "Release $Tag already exists on $GitHubRepo."
    Write-Host "Uploading artifacts to existing release (use --clobber to overwrite)..."
    foreach ($file in $UploadFiles) {
        Write-Host "  Uploading: $(Split-Path $file -Leaf)"
        & gh release upload $Tag $file --repo $GitHubRepo --clobber
        if ($LASTEXITCODE -ne 0) {
            throw "Upload failed for: $file"
        }
    }
} else {
    # Create release and upload in one step
    Write-Host "Creating release $Tag on $GitHubRepo..."
    $CreateArgs += $UploadFiles
    & gh @CreateArgs
    if ($LASTEXITCODE -ne 0) {
        throw "gh release create failed for tag $Tag."
    }
}

# Clean up temp notes file
Remove-Item $NotesTmp -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Release published ==="
Write-Host "  Tag  : $Tag"
Write-Host "  URL  : https://github.com/$GitHubRepo/releases/tag/$Tag"
Write-Host ""
