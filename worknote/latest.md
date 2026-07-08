# AIR-0216/0218 Windows Release Pipeline

**Date**: 2026-07-08
**Status**: DONE (feature/AIR-0216-release-pipeline)

## What Changed

- `tools/build_windows.ps1` — full rewrite: auto-increment build, SHA256 sidecars, -Channel param, build summary
- `tools/release_github.ps1` — new: gh CLI release create/upload, draft/prerelease support
- `packaging/windows/build_counter.txt` — new: persistent build counter (starts at 215)
- `.github/workflows/windows-release.yml` — full rewrite: build + upload-artifact + release + counter commit
- `project_status/RELEASE_PROCESS.md` — new: full release workflow docs, rollback procedure
- `project_status/QA_AIR_0215_E2E.md` — Scenario 8 added (release rollback no-downgrade)
- `worknote/AIR-0216.md`, `AIR-0217.md`, `AIR-0218.md` — new worknotes

## Release Artifact Standard

```
release/
  AIRStudio-{v}-win-x64.zip         portable archive
  AIRStudio-{v}-win-x64.zip.sha256  SHA256 sidecar
  AIRStudioSetup-{v}.exe            installer
  AIRStudioSetup-{v}.exe.sha256     SHA256 sidecar
  latest.json                       update manifest
  latest.json.sha256                SHA256 sidecar
```

## Next
- Create PR for feature/AIR-0216-release-pipeline (after PR #67 merges)
- AIR-0217: Real-install E2E QA (manual, 8 scenarios)
- AIR-0219: Canonical export contract (KI-001)
