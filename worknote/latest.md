# Build 216 — First Real Installer Generated

**Date**: 2026-07-08
**Status**: DONE — artifacts in `release/`

## PRs Merged
- PR #67 (AIR-0214/0215) → main: 2026-07-08T02:21:07Z
- PR #68 (AIR-0216/0218) → main: 2026-07-08T02:21:39Z

## Build Results (Version 2.0.0, Build 216, Channel stable)

| Artifact | Size | SHA256 |
|----------|------|--------|
| AIRStudioSetup-2.0.0.exe | 344.08 MB | ae90a183601518321643b41d01f79a188c7a3c5cb9f58a79800914ce229c97f3 |
| AIRStudio-2.0.0-win-x64.zip | 448.11 MB | 8e73e310a7c907afa2c3467a6643baa14f53583c61c840dd7eeaefd3ffa85d12 |
| latest.json | 481 bytes | 462867622589c52729ec6abb34e2bb4f52e2752fdaca0221c7d09426ed478430 |

All `.sha256` sidecars present and verified. Build counter at 216 (committed to main).

## Build Environment Notes
- Inno Setup 6.7.3 installed to `C:\Projects\InnoSetup6\ISCC.exe` (not in Program Files — installed without admin)
- PyInstaller 6.21.0 installed in venv
- To rebuild: add `C:\Projects\InnoSetup6` to PATH, then run `.\tools\build_windows.ps1 -Version X.Y.Z -Channel stable`

## Next
- Publish to GitHub Releases: `.\tools\release_github.ps1 -Version 2.0.0 -Build 216`
- AIR-0217: Real-install E2E QA (manual, 8 scenarios from QA_AIR_0215_E2E.md)
- AIR-0219: Canonical export contract (KI-001)
