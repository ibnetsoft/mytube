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
- `ae_mouth_worker`
- `comfy_scene_video_worker`
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

`ae_highlight_worker` first checks env vars, then discovers the newest installed
After Effects. It renders 1920×1080 by default and imports a supplied
`scene.metadata.psd_layer_asset` as a layered composition when the asset is a
PSD. A `psd_layer_plan` alone does not create that source asset. Its default
queue is submitted `std_projects`; set `AE_RENDER_PREGEN_TOPICS=1` only if
pre-submission topic rendering is intentionally wanted.
On AE 2026 the render queue writes H.264 MP4 directly. The worker waits for the
project file even when the `AfterFX.com -r` launcher returns before AE finishes
its asynchronous JSX execution. A crash-recovery dialog still requires the
desktop session to be available. The worker recognizes the AE crash-recovery
dialog and selects its Continue button. An unattended Windows service session
without an interactive desktop cannot use this recovery path.

Each scene keeps an input-scoped checkpoint under the local worker temp
directory. For submitted projects, AE leaves the validated MP4 on this host
and records its path in the scene asset by default. A topic can set
`ae_scene_delivery=gcs` at registration or project claim to upload its scene
clips for web preview or another render host. The topic choice takes priority
over the host-wide `AE_SCENE_DELIVERY` fallback. Pre-submission topic rendering
still defaults to GCS unless the topic explicitly chooses local. A restart reuses valid
downloads, the AE project, and the rendered MP4. A failed scene waits 30 seconds, then
backs off exponentially; after three attempts it is marked `needs_attention`.
The worker continues with other scenes. Change `AE_HIGHLIGHT_MAX_ATTEMPTS` to
adjust the limit, or use `--force` after fixing the failure to retry a scene
that needs attention. Keep the checkpoint directory when restarting the host.

Useful commands:

```powershell
python worker/ae_highlight_worker.py --dry-run --topic-limit 20
python worker/ae_highlight_worker.py --loop
```

## Premiere Final Worker

`premiere_final_worker` handles submitted user projects after approval. It:

1. Polls submitted `std_projects`.
2. Finds scene media, preferring AE clips over still images.
3. Copies AE clips from this host after checking their path, byte count, and
   playable duration; downloads other assets from GCS to a local work directory.
4. Creates:
   - `air-premiere-final.xml` (Final Cut Pro 7 XML, imported by Premiere)
   - `air-subtitles.srt`
   - `air-premiere-manifest.json`
   - `air-premiere-bridge.jsx`
   - `air-premiere-package.zip` with the source media and `relink.py`
5. Assembles H.264/AAC media (silent audio when no narration exists), launches
   Adobe Media Encoder with the local export bridge, waits for its completion
   event and MP4 file, adds a selectable subtitle track, then uploads to GCS.
6. Writes `project_payload.render_settings.premiere_final_asset` with
   `status=ready` only after the MP4 upload succeeds.

The final worker waits until every planned AE scene has a ready clip, so it
does not silently use a still image while AE is still rendering. Its local
checkpoint reuses completed downloads, assembly, AME export, and uploads after
a restart. Short AE clips repeat to fill their scene's timeline duration. The
final MP4 uses GCS resumable 8 MB chunks; interrupted uploads query GCS for
the committed byte range and resume, including after a worker restart. Project
failures use 30-second exponential retry and `needs_attention` after three
attempts. Transient GCS upload failures allow 48 attempts by default; set
`PREMIERE_FINAL_UPLOAD_MAX_ATTEMPTS` to adjust that limit. Set
`PREMIERE_FINAL_MAX_ATTEMPTS` to adjust the limit, or rerun with `--force` after
repair. Both workers require their local checkpoint directories to remain on
disk for this reuse; remote database status remains the authoritative queue.
AE and Premiere should therefore run under the same `AIRWORKER_HOME` on the
same machine. During manager shutdown, active Adobe jobs have a bounded drain
(`AIRWORKER_MEDIA_DRAIN_SECONDS`, default two hours) before forced termination.

Useful commands:

```powershell
python worker/premiere_final_worker.py --dry-run --project-limit 20
python worker/premiere_final_worker.py --loop
python worker/air_worker_entry.py --role premiere_final_worker
```

To open an archive on another PC, extract it and run `python relink.py` in the
extracted directory before importing `package/air-premiere-final.xml` into
Premiere. The worker's default `PREMIERE_FINAL_BACKEND=adobe` launches Media
Encoder directly using its ExtendScript command-line hook. It requires a
48 kHz stereo AAC intermediate and the installed `High Quality 1080 HD.epr`
preset; set `PREMIERE_EXPORT_PRESET` to override the preset. Media Encoder
must be closed before each job so the launch script is executed. The bridge
starts and closes its own AME process and does not take over an existing session.
The archive's JSX file remains a manual Premiere import helper. Set
`PREMIERE_FINAL_BACKEND=ffmpeg` for a local FFmpeg-only fallback.

## Why This Split

The user web remains the source of truth for approved script, subtitles, scenes,
media choices, and submission state. Adobe apps are used for heavy post work:

- After Effects: per-scene compositing and motion.
- Premiere Pro: editable FCP7 XML timeline for manual finishing.
- Adobe Media Encoder: automatic final H.264 export.

This keeps expensive Adobe renders after user submission while preserving the
web app as the review and approval surface.
