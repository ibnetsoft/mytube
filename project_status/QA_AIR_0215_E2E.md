# AIR-0215 — E2E QA Checklist (Windows Auto-Update)

**Task**: AIR-0215
**QA Type**: Real-install end-to-end validation
**Prerequisite**: AIR-0215 implementation merged; test machine has a prior install

---

## Test Environment Setup

| Item | Requirement |
|------|-------------|
| OS | Windows 10/11 x64 |
| Prior install | AIRStudioSetup-{old}.exe installed to `%LOCALAPPDATA%\AIRStudio` |
| GitHub Release | New version published with `latest.json`, `AIRStudio-{new}-win-x64.zip`, and `.exe` installer |
| `latest.json` | Must include `version`, `build`, `portable_url`, `sha256` fields |
| Network | Machine must reach GitHub Releases CDN |

---

## Scenario 1 — Normal update (happy path)

**Goal**: Old version detects newer release, downloads, verifies, swaps, relaunches.

### Steps

1. Install old version (e.g. 0.1.0) using the .exe installer.
2. Verify install root contains:
   - `Launcher/AIRLauncher.exe`
   - `Launcher/AIRUpdater.exe`
   - `Launcher/update_config.json`
   - `app/AIRStudio.exe`
   - `app/version.json` → `{"version": "0.1.0", "installed_at": "...", "build": ...}`
   - `current.json`     → `{"version": "0.1.0", "installed_at": "...", "build": ...}`
3. Publish new release (e.g. 0.2.0) to GitHub with correct `latest.json`.
4. Launch `AIRLauncher.exe`.

### Expected results

| Check | Expected |
|-------|----------|
| `launcher.log` — `[EVENT] update_check_started` | Present |
| `launcher.log` — `[EVENT] download_started version=0.2.0` | Present |
| `launcher.log` — `[EVENT] download_completed` | Present with byte count |
| `launcher.log` — `[EVENT] sha256_verified` | Present |
| `updater.log` — `[EVENT] update_check_started` | Present |
| `updater.log` — `[EVENT] extract_completed` | Present |
| `updater.log` — `[EVENT] swap_completed version=0.2.0` | Present |
| `updater.log` — `[EVENT] app_launched` | Present |
| `app/AIRStudio.exe` | Now 0.2.0 build |
| `app/version.json.version` | `"0.2.0"` |
| `app/version.json.build` | Matches `latest.json.build` |
| `current.json.version` | `"0.2.0"` |
| `current.json.installed_at` | UTC ISO-8601 timestamp of swap |
| `current.json.build` | Matches `latest.json.build` |
| `Launcher/AIRLauncher.exe` | **Unchanged** (still old launcher binary) |
| `app_backup/` | Absent (cleaned up) |
| `app_new/` | Absent (cleaned up) |
| Login screen | Shown after update completes |

---

## Scenario 2 — Already up to date (no update)

**Goal**: Launcher detects same version → launches existing app with no download.

### Steps

1. Install version 0.2.0.
2. Publish `latest.json` with `version = "0.2.0"` (same as installed).
3. Launch `AIRLauncher.exe`.

### Expected results

| Check | Expected |
|-------|----------|
| `launcher.log` — `Already up to date` | Present |
| `updater.log` | No new entries (updater not spawned) |
| App | Launches directly without update |

---

## Scenario 3 — SHA256 mismatch (corrupted download)

**Goal**: Update is aborted immediately when hash does not match; existing app is untouched.

### Steps

1. Install old version 0.1.0.
2. Publish `latest.json` with a wrong `sha256` value.
3. Launch `AIRLauncher.exe`.

### Expected results

| Check | Expected |
|-------|----------|
| `launcher.log` — `SHA256 mismatch` | Present with expected vs actual hash |
| `launcher.log` — Updater spawned | **NOT present** |
| `updater.log` | No new entries |
| `app/version.json.version` | Still `"0.1.0"` (unchanged) |
| `current.json.version` | Still `"0.1.0"` (unchanged) |
| App | Launches existing 0.1.0 |
| Temp ZIP | Deleted (cleaned up from `%TEMP%/air_update_*`) |

---

## Scenario 4 — Swap failure → rollback recovery

**Goal**: If `app_new/ → app/` rename fails after `app/ → app_backup/`, the old app is restored.

### Steps (simulated)

1. Install old version 0.1.0.
2. Before swap step 5 completes, lock `app_new/` directory (e.g. hold a file handle).
   *(In practice: simulate by temporarily renaming `app_new/` during test.)*
3. Trigger update (or run `AIRUpdater.exe` manually with `--root`, `--package`, `--version`).

### Expected results

| Check | Expected |
|-------|----------|
| `updater.log` — `[EVENT] rollback_executed` | Present |
| `updater.log` — `Rollback successful` | Present |
| `app/` | Restored (contents of original 0.1.0) |
| `app_backup/` | Absent (removed after rollback) |
| `current.json.version` | Still `"0.1.0"` |
| App | Launches existing 0.1.0 after rollback |

---

## Scenario 5 — Launcher startup recovery (app/ absent, app_backup/ present)

**Goal**: If a previous swap left app/ missing but app_backup/ intact, the launcher restores it.

### Steps (simulated)

1. Install old version 0.1.0.
2. Manually rename `app/` → `app_backup/` (simulate mid-swap reboot).
3. Launch `AIRLauncher.exe`.

### Expected results

| Check | Expected |
|-------|----------|
| `launcher.log` — `app/ is missing but app_backup/ found` | Present |
| `launcher.log` — `Recovery successful` | Present |
| `app/` | Restored from `app_backup/` |
| `app_backup/` | Absent |
| App | Launches successfully |

---

## Scenario 6 — Launcher guard (AIRLauncher.exe in payload)

**Goal**: AIRLauncher.exe present in ZIP payload root is removed before swap; Launcher/ is not touched.

### Steps (simulated)

1. Create a test ZIP with `app/AIRStudio.exe` AND `app/AIRLauncher.exe`.
2. Run `AIRUpdater.exe --root ... --package ... --version 0.3.0 --sha256 ...`.

### Expected results

| Check | Expected |
|-------|----------|
| `updater.log` — `[GUARD] AIRLauncher.exe found in app payload root` | Present |
| `updater.log` — `[GUARD] AIRLauncher.exe removed from payload` | Present |
| `Launcher/AIRLauncher.exe` | **Unchanged** |
| `app/AIRLauncher.exe` | **Not present** after swap |
| `app/AIRStudio.exe` | Present (new version) |

---

## Scenario 7 — Version detection priority

**Goal**: Each fallback in the version chain is exercised.

| State | Expected source | Expected version |
|-------|----------------|-----------------|
| `current.json` present + valid | `current.json` | Correct |
| `current.json` absent, `app/version.json` valid | `app/version.json` | Correct |
| Both JSON absent, exe has VersionInfo | exe VersionInfo (PowerShell) | Correct |
| All three absent/invalid | `"0.0.0"` default | `0.0.0` |

---

## Log File Locations

```
%APPDATA%\AIRStudio\logs\launcher.log
%APPDATA%\AIRStudio\logs\updater.log
```

---

---

## Scenario 8 — Release rollback (lower version re-published)

**Goal**: Verify that when `latest.json` points to a version **lower** than what is
installed, the Launcher does NOT downgrade. (True rollback requires reinstall.)

### Steps

1. Install version 0.2.0.
2. Set `latest.json.version = "0.1.0"` (lower than installed).
3. Launch `AIRLauncher.exe`.

### Expected results

| Check | Expected |
|-------|----------|
| `launcher.log` — `Already up to date` | Present |
| App | Launches 0.2.0 (no downgrade) |
| `current.json.version` | `"0.2.0"` (unchanged) |

> **Note**: Downgrade requires reinstall via the installer `.exe`.
> See `RELEASE_PROCESS.md` for rollback procedure.

---

## Pass Criteria

All 8 scenarios must pass. No scenario may leave:
- The install root in a non-bootable state
- `Launcher/AIRLauncher.exe` modified
- `current.json` or `app/version.json` with a version different from what was installed
- A SHA256 mismatch silently ignored
- An unintended downgrade applied automatically
