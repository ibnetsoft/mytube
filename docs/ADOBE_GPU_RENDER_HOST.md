# Adobe GPU Render Host

This document describes the Windows GPU host expected to run current Adobe
After Effects and Premiere Pro automation.

## Host Role

The GPU Adobe host is a render/post-production worker, not the script-writing
machine. It should run:

```powershell
python worker/air_worker_entry.py --profile render_only
```

`render_only` now starts:

- `render_worker`
- `ae_highlight_worker`
- `premiere_final_worker`
- `remote_drive_worker`
- `local_api`

Use `content_only` on machines that do not have Adobe apps installed.

## Adobe Path Discovery

The worker auto-detects the newest installed apps under:

- `C:\Program Files\Adobe`
- `C:\Program Files (x86)\Adobe`

It can also be pinned explicitly:

```powershell
$env:AE_AFTERFX_PATH="C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\AfterFX.com"
$env:AE_AERENDER_PATH="C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\aerender.exe"
$env:PREMIERE_PATH="C:\Program Files\Adobe\Adobe Premiere Pro 2026\Adobe Premiere Pro.exe"
$env:AME_PATH="C:\Program Files\Adobe\Adobe Media Encoder 2026\Adobe Media Encoder.exe"
```

Check detection:

```powershell
python -c "import sys,json; sys.path.insert(0,'worker'); import adobe_tools; print(json.dumps(adobe_tools.capability_report(), ensure_ascii=False, indent=2))"
```

## AE Worker

`ae_highlight_worker` no longer assumes CS6 paths. It first checks env vars, then
discovers the newest installed After Effects. Existing CS6-compatible JSX still
works, while newer hosts can render faster through current AE/aerender.

Useful commands:

```powershell
python worker/ae_highlight_worker.py --dry-run --topic-limit 20
python worker/ae_highlight_worker.py --loop
```

## Premiere Final Worker

`premiere_final_worker` handles submitted user projects after approval. It:

1. Polls submitted `std_projects`.
2. Finds scene media, preferring AE clips over still images.
3. Downloads assets from GCS to a local ASCII work directory.
4. Creates:
   - `air-premiere-final.fcpxml`
   - `air-subtitles.srt`
   - `air-premiere-manifest.json`
   - `air-premiere-bridge.jsx`
5. Uploads the package to GCS.
6. Writes `project_payload.render_settings.premiere_final_asset`.

Useful commands:

```powershell
python worker/premiere_final_worker.py --dry-run --project-limit 20
python worker/premiere_final_worker.py --loop
python worker/air_worker_entry.py --role premiere_final_worker
```

The first implementation deliberately stops at a durable Premiere package. The
package is the boundary for a current Premiere UXP/AME export bridge. That
bridge can consume `air-premiere-manifest.json`, open/import the timeline, apply
captions/audio policy, export the final MP4, and write the final GCS result back
to the same `premiere_final_asset` record.

## Why This Split

The user web remains the source of truth for approved script, subtitles, scenes,
media choices, and submission state. Adobe apps are used for heavy post work:

- After Effects: per-scene compositing and motion.
- Premiere Pro: final timeline assembly, subtitle/audio layout, and export.

This keeps expensive Adobe renders after user submission while preserving the
web app as the review and approval surface.
