# AIR Studio — Windows Bootstrap & Auto-Update System

**Tasks**: AIR-0214 (foundation), AIR-0215 (hardening)
**Status**: Production-ready

---

## Overview

The Windows distribution uses a two-stage bootstrap to apply updates safely
before the login screen ever appears.

```
User double-clicks AIRLauncher.exe
       │
       ├─ auto-recover: if app/ absent + app_backup/ present → restore
       ├─ cleanup leftover artefacts (app_new/, extract/)
       ├─ read local version: current.json → app/version.json → exe VersionInfo → 0.0.0
       ├─ fetch latest.json from GitHub Releases
       │
       ├─── version matches? ──► launch app/AIRStudio.exe  (normal boot)
       │
       └─── newer version? ──► download ZIP
                               │
                               ├─ SHA256 verify (Launcher)
                               ├─ hash fail? → launch existing app (no change)
                               │
                               └─ hash OK? → spawn AIRUpdater.exe → exit
                                             │
                                             ├─ SHA256 re-verify (Updater)
                                             ├─ extract → app_new/
                                             ├─ guard: Launcher.exe not in payload
                                             ├─ atomic swap: app/ → app_backup/ → app_new/ → app/
                                             ├─ write current.json + app/version.json
                                             ├─ cleanup app_backup/
                                             └─ launch app/AIRStudio.exe
```

---

## Directory Layout (Install Root)

```
%LOCALAPPDATA%\AIRStudio\
  Launcher\
    AIRLauncher.exe          ← stable entry point (NEVER updated by payload swap)
    AIRUpdater.exe           ← applies payload swaps (NEVER updated by payload swap)
    update_config.json       ← {"manifest_url": "https://..."}
  app\
    AIRStudio.exe            ← main PyInstaller bundle
    version.json             ← full version record (see schema below)
    templates/
    static/
    ...
  current.json               ← full version record (written by updater + build script)
```

**Rule**: The `Launcher/` directory is immutable between installer versions.
Only a new installer `.exe` replaces `AIRLauncher.exe` or `AIRUpdater.exe`.
The app-payload swap touches only `install_root/app/`.

---

## Version Record Schema (AIR-0215)

Both `current.json` and `app/version.json` use the same canonical schema:

```json
{
  "version":      "1.2.3",
  "installed_at": "2026-07-08T12:34:56Z",
  "build":        215
}
```

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Semantic version (e.g. "1.2.3") |
| `installed_at` | string | UTC ISO-8601 timestamp of swap completion |
| `build` | integer | Task/build ID (e.g. 215 for AIR-0215) |

---

## GitHub Releases Manifest (`latest.json`)

Published as a release asset on every GitHub Release.

```json
{
  "version":       "1.2.3",
  "build":         215,
  "channel":       "stable",
  "mandatory":     false,
  "installer_url": "https://github.com/OWNER/REPO/releases/download/v1.2.3/AIRStudioSetup-1.2.3.exe",
  "portable_url":  "https://github.com/OWNER/REPO/releases/download/v1.2.3/AIRStudio-1.2.3-win-x64.zip",
  "sha256":        "<hex digest of the portable ZIP>",
  "notes":         "Release notes here"
}
```

The `manifest_url` in `Launcher/update_config.json` should point to the **latest** alias:
```
https://github.com/OWNER/REPO/releases/latest/download/latest.json
```

---

## Version Detection Priority (AIRLauncher)

```
1. <root>/current.json         → version field
2. <root>/app/version.json     → version field     (fallback)
3. <root>/app/AIRStudio.exe    → PE FileVersion via PowerShell  (fallback)
4. "0.0.0"                                         (default)
```

---

## Atomic Swap Strategy (AIRUpdater)

The critical invariant: **the existing `app/` is never deleted until the new one is verified and ready**.

```
Step 0  cleanup app_backup/, app_new/ from any prior failed run
Step 1  SHA256 verify package (abort immediately on mismatch)
Step 2  extract ZIP → app_new/
Step 3  guard: AIRLauncher.exe not in payload
Step 4  os.rename(app/,     app_backup/)   ← atomic on same NTFS volume
Step 5  os.rename(app_new/, app/)          ← atomic on same NTFS volume
Step 6  write current.json + app/version.json (full schema)
Step 7  rmtree(app_backup/)   (cleanup)
Step 8  launch app/AIRStudio.exe
```

**Failure recovery** (between steps 4–5):
- If step 5 fails and `app/` is absent but `app_backup/` exists →
  `os.rename(app_backup/, app/)` restores the old version automatically.

**Launcher startup recovery** (after reboot mid-swap):
- If `app/` is absent and `app_backup/` exists →
  AIRLauncher restores before proceeding to update check or launch.

---

## SHA256 Verification Chain

SHA256 is verified **twice** for defence in depth:

| Where | File | Outcome on mismatch |
|-------|------|---------------------|
| AIRLauncher | Downloaded ZIP | Delete temp file, launch existing app unchanged |
| AIRUpdater  | Downloaded ZIP | Delete temp file, abort — no extraction, no swap |

---

## Structured Log Events

Both components log `[EVENT]` markers for machine-parseable monitoring.

| Event | Component | When |
|-------|-----------|------|
| `update_check_started` | Launcher + Updater | Before manifest fetch / before extraction |
| `download_started`     | Launcher | Before `download_file()` |
| `download_completed`   | Launcher | After ZIP written to disk |
| `sha256_verified`      | Launcher + Updater | After hash comparison passes |
| `extract_completed`    | Updater | After `zipfile.extractall()` |
| `swap_completed`       | Updater | After step 5 rename succeeds |
| `rollback_executed`    | Updater | When rollback is triggered |
| `app_launched`         | Updater | After `subprocess.Popen` |

### Log file locations

```
%APPDATA%\AIRStudio\logs\launcher.log
%APPDATA%\AIRStudio\logs\updater.log
```

---

## Build Pipeline

`tools/build_windows.ps1 -Version 1.2.3 -Build 215`

1. PyInstaller → `dist/AIRStudio/` (onedir bundle)
2. Copy to `release/staging/AIRStudio/app/`
3. Write `release/staging/AIRStudio/app/version.json`  (full schema with build + installed_at)
4. Build `AIRLauncher.exe` + `AIRUpdater.exe` → `Launcher/`
5. Write `Launcher/update_config.json` + root `current.json` (full schema)
6. Compress staging → `release/AIRStudio-{ver}-win-x64.zip`
7. Compute SHA256, write `release/latest.json` (includes `build` field)
8. (Optional) Run Inno Setup → `release/AIRStudioSetup-{ver}.exe`

---

## E2E QA

See `project_status/QA_AIR_0215_E2E.md` for the full 7-scenario QA checklist.
