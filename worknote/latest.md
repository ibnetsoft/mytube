# AIR-0215 Windows Updater Hardening

**Date**: 2026-07-08
**Status**: DONE (feature/AIR-0214-windows-installer)

## What Changed

- `packaging/windows/launcher/AIRUpdater.py` — SHA256 re-verify before extraction, --sha256/--build args, _guard_launcher_not_overwritten(), full version schema, [EVENT] log markers
- `packaging/windows/launcher/AIRLauncher.py` — _exe_version() fallback (PowerShell), _recover_app_if_needed(), updated cleanup order, [EVENT] markers, passes --sha256+--build to updater
- `tools/build_windows.ps1` — -Build param, full current.json/version.json schema, build field in latest.json
- `packaging/windows/latest.example.json` — added build field
- `project_status/BOOTSTRAP.md` — rewritten with full AIR-0215 hardening docs
- `project_status/QA_AIR_0215_E2E.md` — new 7-scenario real-install E2E QA checklist

## Key Facts

- SHA256 verified TWICE: Launcher (before spawn) + Updater (before extraction)
- current.json schema: {"version", "installed_at" (UTC ISO-8601), "build" (int)}
- Version priority: current.json → app/version.json → exe VersionInfo → 0.0.0
- Startup recovery: _recover_app_if_needed() runs before cleanup and update check
- Launcher guard: AIRLauncher.exe removed from payload if present; payload must not be Launcher/
- [EVENT] 8 structured markers across Launcher + Updater log files
- py_compile: both files pass cleanly

## Next
- PR #66 or #67 for AIR-0214+0215 combined
- Real-install QA per QA_AIR_0215_E2E.md
- AIR-0216: Canonical export contract (KI-001)
