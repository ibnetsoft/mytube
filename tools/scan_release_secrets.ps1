#Requires -Version 5.1
<#
.SYNOPSIS
    AIR-0225B incident response: fail the build if a Supabase service_role key
    (or anything shaped like one) made it into a release artifact.

.DESCRIPTION
    Supabase service_role keys are JWTs: three base64url segments separated by
    dots, whose decoded payload contains "role":"service_role". This script scans
    every file under the given path(s) - including inside .zip archives - for
    JWT-shaped substrings, decodes ONLY the payload segment in memory to check the
    role claim, and never prints the candidate token or its decoded contents
    anywhere. Only a pass/fail boolean per finding is reported.

    It also separately flags:
      - the literal string "SUPABASE_SERVICE_ROLE_KEY=" appearing anywhere
        (catches the env-var-style leak even if the value itself isn't a JWT,
        e.g. a placeholder or a differently-shaped secret)
      - the mere presence of a ".env" file anywhere in the scanned tree, since a
        packaged desktop app should never ship one at all after AIR-0225B

    Run this BEFORE "Publish GitHub Release" in the Windows release workflow.
    A non-zero exit code must block the publish step.

.PARAMETER Path
    One or more files/directories to scan (recursed). Typically:
      release/staging/AIRStudio
      release/*.zip
      release/*.exe
      dist/AIRStudio

.EXAMPLE
    .\tools\scan_release_secrets.ps1 -Path release/staging/AIRStudio, release
#>
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path
)

$ErrorActionPreference = "Stop"

# Three base64url segments separated by dots, each long enough to be a real JWT
# segment (short accidental matches like "a.b.c" in prose are filtered by length).
$JwtPattern = [regex]'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'
$EnvVarLiteralPattern = [regex]'SUPABASE_SERVICE_ROLE_KEY\s*='

$script:FindingsCount = 0
$script:ScannedFiles = 0
$script:EnvFilesFound = @()

function Test-JwtIsServiceRole {
    param([string]$Token)
    try {
        $parts = $Token.Split('.')
        if ($parts.Count -lt 2) { return $false }
        $payloadB64 = $parts[1]
        # base64url -> base64
        $payloadB64 = $payloadB64.Replace('-', '+').Replace('_', '/')
        switch ($payloadB64.Length % 4) {
            2 { $payloadB64 += '==' }
            3 { $payloadB64 += '=' }
        }
        $bytes = [Convert]::FromBase64String($payloadB64)
        $json = [System.Text.Encoding]::UTF8.GetString($bytes)
        # Never write $json anywhere - inspect in memory only, discard immediately.
        $isServiceRole = $json -match '"role"\s*:\s*"service_role"'
        $json = $null
        return [bool]$isServiceRole
    } catch {
        return $false
    }
}

function Scan-TextBlob {
    param(
        [string]$Content,
        [string]$SourceLabel
    )

    $script:ScannedFiles++

    $jwtMatches = $JwtPattern.Matches($Content)
    foreach ($m in $jwtMatches) {
        $isServiceRole = Test-JwtIsServiceRole -Token $m.Value
        if ($isServiceRole) {
            $script:FindingsCount++
            Write-Host "##[error] SERVICE_ROLE JWT DETECTED in: $SourceLabel (candidate value NOT shown)"
        }
    }

    if ($EnvVarLiteralPattern.IsMatch($Content)) {
        $script:FindingsCount++
        Write-Host "##[error] Literal 'SUPABASE_SERVICE_ROLE_KEY=' string DETECTED in: $SourceLabel (value NOT shown)"
    }
}

function Scan-File {
    param([string]$FilePath)

    $leaf = Split-Path $FilePath -Leaf
    if ($leaf -ieq ".env") {
        $script:EnvFilesFound += $FilePath
        Write-Host "##[error] .env file present in packaged output: $FilePath"
    }

    if ($leaf -match '\.(zip)$') {
        $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("secretscan_" + [Guid]::NewGuid().ToString("N"))
        try {
            New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
            Expand-Archive -LiteralPath $FilePath -DestinationPath $tempDir -Force
            Get-ChildItem -LiteralPath $tempDir -Recurse -File | ForEach-Object {
                Scan-File -FilePath $_.FullName
            }
        } finally {
            if (Test-Path $tempDir) {
                Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        return
    }

    try {
        # Read raw bytes and interpret as Latin1 so binary files (exe, pyz, frozen
        # modules) don't break the scan - JWTs / the literal env-var string are
        # ASCII and survive a Latin1 round-trip byte-for-byte.
        $bytes = [System.IO.File]::ReadAllBytes($FilePath)
        $content = [System.Text.Encoding]::GetEncoding("ISO-8859-1").GetString($bytes)
        $bytes = $null
        Scan-TextBlob -Content $content -SourceLabel $FilePath
        $content = $null
    } catch {
        Write-Warning "Could not scan '$FilePath': $($_.Exception.Message)"
    }
}

Write-Host "=== AIR-0225B release secret scan ==="
foreach ($p in $Path) {
    if (-not (Test-Path $p)) {
        Write-Warning "Path not found, skipping: $p"
        continue
    }
    $item = Get-Item -LiteralPath $p
    if ($item.PSIsContainer) {
        Get-ChildItem -LiteralPath $p -Recurse -File | ForEach-Object { Scan-File -FilePath $_.FullName }
    } else {
        Scan-File -FilePath $item.FullName
    }
}

Write-Host ""
Write-Host "Files scanned: $script:ScannedFiles"
Write-Host "Findings: $script:FindingsCount"
if ($script:EnvFilesFound.Count -gt 0) {
    Write-Host "'.env' files present: $($script:EnvFilesFound.Count)"
    foreach ($f in $script:EnvFilesFound) { Write-Host "  - $f" }
}

if ($script:FindingsCount -gt 0 -or $script:EnvFilesFound.Count -gt 0) {
    Write-Host "##[error] Secret scan FAILED. Blocking release."
    exit 1
}

Write-Host "Secret scan passed - no service_role JWT, no SUPABASE_SERVICE_ROLE_KEY literal, no .env file found."
exit 0
