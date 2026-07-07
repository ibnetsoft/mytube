# AIR Studio — Windows Release Process

**Task**: AIR-0216
**Status**: Implemented

---

## Release artifact structure

Every release must produce exactly these files in `release/`:

```
release/
  AIRStudio-{version}-win-x64.zip           ← portable archive
  AIRStudio-{version}-win-x64.zip.sha256    ← sha256sum format sidecar
  AIRStudioSetup-{version}.exe              ← Inno Setup installer
  AIRStudioSetup-{version}.exe.sha256       ← sha256sum format sidecar
  latest.json                               ← update manifest (auto-fetched by Launcher)
  latest.json.sha256                        ← sha256sum format sidecar
```

`.sha256` sidecar format (standard `sha256sum` compatible):
```
<lowercase hex>  <filename>
```

---

## Build number auto-increment

`packaging/windows/build_counter.txt` holds the current integer build number.

- **Manual build**: `build_windows.ps1` reads and increments this file automatically.
- **CI build**: GitHub Actions reads the file, computes `next = current + 1`, passes it to `build_windows.ps1`, then commits the updated counter back (`[skip ci]`).
- **Explicit override**: Pass `-Build <int>` to `build_windows.ps1` to override.

---

## Manual release workflow

### Step 1 — Build

```powershell
# Build with auto-increment build number
.\tools\build_windows.ps1 -Version 1.2.3

# Or specify build number explicitly
.\tools\build_windows.ps1 -Version 1.2.3 -Build 220 -Channel stable
```

Produces all artifacts in `release/`.

### Step 2 — Publish to GitHub Releases

```powershell
# Authenticate once (if not already)
gh auth login

# Publish stable release
.\tools\release_github.ps1 -Version 1.2.3 -Build 220

# Publish draft (review on GitHub before making public)
.\tools\release_github.ps1 -Version 1.2.3 -Build 220 -Draft

# Publish beta / pre-release
.\tools\release_github.ps1 -Version 1.2.3-beta -Build 220 -Channel beta -Prerelease
```

### Step 3 — Verify update manifest is live

```
https://github.com/ibnetsoft/mytube/releases/latest/download/latest.json
```

Check:
- `version` matches the release
- `build` matches the counter
- `sha256` matches the ZIP artifact
- `portable_url` is downloadable

---

## Automated release workflow (AIR-0218 / GitHub Actions)

File: `.github/workflows/windows-release.yml`

### Trigger: Push version tag

```bash
git tag v1.2.3
git push origin v1.2.3
```

The workflow:
1. Detects version from tag name
2. Auto-increments build counter
3. Installs Python 3.13 + Inno Setup
4. Runs `build_windows.ps1`
5. Uploads artifacts to workflow run (30-day retention)
6. Runs `release_github.ps1` → creates GitHub Release
7. Commits updated `build_counter.txt` back to repo

### Trigger: Manual dispatch

Navigate to **Actions → Windows Release → Run workflow**.
Supply `version`, `channel`, `draft`, `prerelease` inputs.

---

## latest.json schema (canonical)

```json
{
  "version":       "1.2.3",
  "build":         220,
  "channel":       "stable",
  "mandatory":     false,
  "installer_url": "https://github.com/ibnetsoft/mytube/releases/download/v1.2.3/AIRStudioSetup-1.2.3.exe",
  "portable_url":  "https://github.com/ibnetsoft/mytube/releases/download/v1.2.3/AIRStudio-1.2.3-win-x64.zip",
  "sha256":        "<lowercase hex SHA256 of the portable ZIP>",
  "notes":         "AIR Studio v1.2.3 (build 220, channel stable)"
}
```

---

## Release rollback procedure

To roll back to a previous version (e.g. v1.1.0):

1. Republish `latest.json` from v1.1.0's release:
   ```bash
   gh release download v1.1.0 --pattern "latest.json" -D /tmp/rollback
   gh release upload latest /tmp/rollback/latest.json --repo ibnetsoft/mytube --clobber
   ```
   *(Note: update the `"portable_url"` and `"sha256"` in the file to point to v1.1.0 artifacts.)*

2. Update `latest.json` to reference v1.1.0 version, build, and download URL.

3. Running Launchers will detect that `latest.json.version < installed.version` — **no downgrade**.
   To force a rollback, either:
   - Lower the `version` field in `latest.json` and set `"mandatory": true`, OR
   - Direct users to reinstall from the v1.1.0 `.exe` installer.

> **Important**: AIRLauncher compares versions with `version_tuple()`. A "rollback" via
> `latest.json` only works if the published version is **higher** than the installed version.
> For true downgrade, a full reinstall via the installer is required.

---

## CI prerequisites (GitHub repository secrets / settings)

| Item | Value |
|------|-------|
| `GITHUB_TOKEN` | Auto-provided by Actions (no setup needed) |
| `contents: write` | Set in workflow `permissions` block |
| Inno Setup | Installed via `choco install innosetup` in CI |
| Python 3.13 | Installed via `actions/setup-python@v5` |

---

## Checklist before each release

- [ ] `packaging/windows/build_counter.txt` reflects expected next build number
- [ ] `main` branch is clean and all tests pass
- [ ] `py_compile` passes for `AIRLauncher.py` and `AIRUpdater.py`
- [ ] Version in `main.py` (`version="x.y.z"`) matches release version
- [ ] `release/` directory is clean (or `release/staging/` is deleted)
- [ ] Inno Setup installed locally (if building installer manually)
- [ ] `gh auth status` shows authenticated (if publishing manually)
