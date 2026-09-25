# After Effects Highlight Pipeline

## Purpose

After Effects is an optional highlight-render stage, not the main video assembler.
The normal production path remains:

1. Codex/Hermes script worker creates script, scenes, image prompts, video prompts, SFX cues, and `ae_effect_plan`.
2. Scene image workers create or publish still images to storage.
3. The AE-capable render worker downloads only selected highlight scene images and renders short effect clips.
4. FFmpeg assembles ordinary scene clips, AE highlight clips, narration, subtitles, SFX, BGM, and final output.

Use AE for compositing work that is awkward to maintain as pure FFmpeg filters:

- wuxia sword aura, qi rings, particles, glow trails
- moving fog, moon rays, light shafts
- localized distortion, heat shimmer, impact pulses
- ink-wash memory reveals, paper-grain flicker
- masked foreground/background effect layers

Keep pan, zoom, scroll, simple flash, subtitles, concatenation, final encoding, and upload in the FFmpeg pipeline.

## Script Worker Contract

The script worker may run on any capable machine. It does not need After Effects installed.
It emits optional per-scene AE hints under `structure.ae_effect_plans` and `scene.ae_effect_plan`.

Example:

```json
{
  "scene_number": 8,
  "duration_seconds": 5,
  "ae_effect_plan": {
    "enabled": true,
    "preset": "wuxia_sword_aura",
    "priority": 4,
    "duration_seconds": 5,
    "direction": "After Effects highlight: cyan sword aura, qi particles, fog, glow streaks, and mild turbulent distortion.",
    "fallback": "ffmpeg_basic_motion"
  }
}
```

Current preset names:

- `wuxia_sword_aura`
- `memory_ink_wash`
- `anger_impact`
- `moon_fog_reveal`

The plan is advisory. If no AE worker is available, or a render fails, the scene must fall back to standard FFmpeg motion.

## AE Worker Requirement

Only the AE render stage must run on a Windows machine with After Effects installed.
For the current test machine, the detected paths are:

- `C:/Program Files/Adobe/Adobe After Effects CS6/Support Files/AfterFX.exe`
- `C:/Program Files/Adobe/Adobe After Effects CS6/Support Files/aerender.exe`

AE CS6 is acceptable for the highlight worker when presets stay within CS6-compatible effects:

- Shape Layers
- Glow / `ADBE Glo2`
- Fast Blur
- Fractal Noise
- Turbulent Displace
- Radial Wipe
- Add/Screen/Multiply blend modes

Do not depend on current-generation AE plugins, expressions, or project features.

## Job Routing

Recommended capability split:

- `script_worker`: any machine with Codex/Hermes credentials.
- `image_worker`: any machine or external generation path that can publish scene images.
- `ae_render_worker`: Windows only, requires After Effects and storage credentials.
- `final_render_worker`: any machine with FFmpeg and media access.

The AE worker should claim only jobs whose payload requires one of:

```json
{
  "capabilities": ["after_effects_cs6", "windows", "gcs_read_write"]
}
```

Do not route the whole script worker to the AE machine unless the same machine is intentionally doing all stages.

In this repository the concrete worker is `worker/ae_highlight_worker.py`.
It polls `topics_queue` rows whose `pregenerated_structure_status=ready`, finds scenes with
`ae_effect_plan.enabled=true`, downloads the scene image from GCS, renders a short AE clip,
uploads the MP4 back to GCS, and writes the result into that scene:

- `scene.metadata.ae_effect_asset`
- `scene.ae_effect_status`
- `scene.ae_video_url`
- `scene.video_url`

Useful commands:

```powershell
python worker/ae_highlight_worker.py --dry-run --topic-limit 20
python worker/ae_highlight_worker.py --loop
python worker/air_worker_entry.py --role ae_highlight_worker
python worker/cli_status.py --start ae-highlight
python worker/cli_status.py --stop ae-highlight
```

`full` and `render_only` AIR Worker profiles start the AE worker automatically.
`content_only` intentionally does not, so script generation can run on machines without After Effects.

## Storage Flow

Use storage URLs as the boundary between workers.

1. Script worker saves `ae_effect_plan` with scene metadata.
2. Image stage uploads original stills: `gs://.../scenes/scene_008.png`.
3. AE worker downloads the image to an ASCII local job directory, such as `D:/ae_jobs/<job_id>/input/scene_008.png`.
4. AE worker generates JSX and AEP in that job directory.
5. AE worker renders a lossless/intermediate file or PNG sequence.
6. FFmpeg transcodes to production MP4/WebM if needed.
7. Upload worker publishes the result: `gs://.../ae/scene_008_wuxia_sword_aura.mp4`.
8. Final renderer uses the AE clip URL for that scene; otherwise it uses standard FFmpeg motion.

Keep local AE paths ASCII-only. AE CS6 can mishandle Korean or mixed-encoding paths in render logs and scripts.

## Failure Policy

AE is enhancement, not a blocking core dependency.

- If AE is not installed: skip AE jobs and mark them `skipped_no_capability`.
- If AE render fails once: retry once on the same worker after clearing the local job directory.
- If it fails again: mark `failed_fallback_ready` and use FFmpeg basic motion.
- If a preset is unsupported by CS6: mark `unsupported_preset` and use fallback.

Final video production must not be blocked by AE unless the user explicitly requests “AE highlights required.”

## Minimal AE Job Payload

```json
{
  "job_type": "render_ae_highlight",
  "project_id": "project_123",
  "scene_number": 8,
  "source_image_url": "gs://bucket/projects/project_123/scenes/scene_008.png",
  "duration_seconds": 5,
  "fps": 24,
  "width": 720,
  "height": 720,
  "preset": "wuxia_sword_aura",
  "direction": "cyan sword aura, qi particles, fog, glow streaks, mild turbulent distortion",
  "fallback": "ffmpeg_basic_motion",
  "output_url": "gs://bucket/projects/project_123/ae/scene_008_wuxia_sword_aura.mp4"
}
```
