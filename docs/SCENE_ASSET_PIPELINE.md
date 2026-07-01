# LONGFORM SCENE ASSET PIPELINE

## Scope

This document defines how externally generated Longform images and video clips are named, uploaded, matched, stored, reviewed, and restored in AIR Studio.
It records the implementation reviewed and minimally completed by AIR-0109 on 2026-06-28.

## Asset Structure

Primary local table: `image_prompts`

Each row belongs to:

- `project_id`
- `scene_number`

Relevant image fields:

- `image_url`
- `prompt_ko`
- `prompt_en`
- `scene_text`
- `scene_title`

Relevant video fields:

- `video_url`
- `motion_desc`
- `flow_prompt`
- `prompt_en_start`
- `prompt_en_end`

Image and video are independent slots on one scene.
A Scene may retain both an image and a video clip.

## Canonical Filename Rule

Preferred filename:

```text
scene_NNN_<optional-description>.<extension>
```

Examples:

```text
scene_001_crop.png
scene_001_upscaled.png
scene_001_final.webp
scene_001_clip.mp4
scene_012.mp4
```

Also recognized:

```text
s12-final.mp4
003_result.webp
```

Rules:

1. Scene numbering starts at 1.
2. Three-digit zero padding is preferred but not required.
3. The number after `scene`, `sc`, or `s` is authoritative.
4. A leading numeric token is accepted.
5. Filename Scene mapping takes priority over AI semantic matching.

## Scene Mapping Rules

### Filename First

`services/scene_asset_matcher.py::extract_scene_number()` parses the Scene number.

If a valid Scene number exists:

- it must exist in the project Scene set
- image maps to the Scene image slot
- video maps to the Scene video slot
- Gemini is not allowed to override the filename

### AI Fallback

If the filename has no Scene number:

- images are sent to Gemini Vision
- videos use an extracted middle frame
- Gemini receives project Scene descriptions
- returned Scene numbers are validated against the project

### Manual Assignment

For a specific Scene:

- use the Scene card upload control
- use `POST /api/image/upload-scene`
- use the asset library replacement control

AIR-0108 keeps image and video slots independent during replacement.

## 2x2 Crop Mapping

AIR-0109 connects the crop utility to project Scenes.

Entry route:

```text
/image-crop?project_id={project_id}&start_scene={scene_number}
```

Assignment formula:

```text
target_scene = start_scene + (grid_index * 4) + panel_index - 1
```

For one grid starting at Scene 5:

| Panel | Target | Filename |
| --- | --- | --- |
| Top-left | Scene 5 | `scene_005_crop.png` |
| Top-right | Scene 6 | `scene_006_crop.png` |
| Bottom-left | Scene 7 | `scene_007_crop.png` |
| Bottom-right | Scene 8 | `scene_008_crop.png` |

The crop page:

- loads the target project's Scene rows
- shows the destination Scene number on each panel
- disables import when the Scene does not exist
- disables import when the Scene image slot is occupied
- imports one panel or all available panels
- uses the existing Scene upload endpoint
- sends `replace_existing=false`, so the backend rechecks occupancy at write time
- preserves any existing video in the target Scene

The ZIP download uses the same deterministic filenames when project context exists.

## Upscaled Image Reconnection

Recommended workflow:

1. Export or import `scene_001_crop.png`.
2. Upscale externally.
3. Keep the Scene token in the result filename, for example `scene_001_upscaled.png`.
4. Bulk upload on `/image-gen`.
5. AIR Studio maps the file to Scene 1 without Gemini.

If Scene 1 already has an image, safe bulk upload reports the slot as occupied instead of overwriting it.
To intentionally replace it, use the Scene 1 Replace control.

## Video Clip Reconnection

Recommended filename:

```text
scene_001_clip.mp4
```

Bulk upload reads Scene 1 from the filename and updates only the Scene video slot.
Upload order does not control Scene order.

## Order Preservation

- Backend Scene retrieval uses `ORDER BY scene_number`.
- Bulk upload maps by filename or validated AI result, not file selection order.
- The Scene Asset Review panel sorts by `scene_number`.
- Final video clips are listed in Scene order.

## Missing Scene Handling

Current behavior:

- bulk import returns missing image and video Scene lists
- Scene Asset Review shows image/video status
- a Scene with neither image nor video blocks Continue to TTS
- missing video remains a warning because image-only policy is undecided
- crop import marks out-of-range Scene destinations unavailable

## Duplicate Upload Handling

Bulk upload:

- does not overwrite an occupied slot
- reports duplicate files targeting one Scene/media slot
- treats image and video slots independently

Crop import:

- skips an occupied image slot
- imports only empty target image slots
- rejects a race-time occupied slot with HTTP 409 instead of overwriting it

Intentional replacement:

- remains available through the individual Scene Replace control
- does not yet have version history or rollback

## Invalid File Handling

Bulk upload reports:

- unsupported extension
- file too large
- out-of-range Scene number
- invalid AI mapping
- unmatched file

Crop import:

- only receives images accepted by the crop page
- refuses missing or occupied target Scene slots
- surfaces per-panel import errors

## Large Upload Review

Current implementation is safe but not optimized for very large batches.

### Crop

- four HTTP crop requests are made per 2x2 grid
- grids and panels are processed sequentially
- direct project import is also sequential
- this limits memory spikes and accidental duplicate writes
- large batches will take proportionally longer

### Bulk Image/Video Upload

- one multipart request contains all selected files
- full file content is read into memory before storage
- unnumbered videos require middle-frame extraction
- unnumbered assets add Gemini latency
- request timeout and memory pressure can grow with large videos

### Recommended Current Operating Limit

- prefer numbered filenames
- upload manageable batches rather than an entire large project at once
- use 2x2 crop import in small groups
- use individual Scene Replace for intentional corrections

Needs verification:

- packaged desktop behavior with large mixed video batches
- practical batch-size limit by available RAM
- whether resumable/chunked upload is required

## Current Implementation Status

| Capability | Status |
| --- | --- |
| Scene image/video storage | Implemented |
| Independent image/video slots | Implemented |
| Filename Scene parsing | Implemented |
| AI fallback matching | Implemented |
| Scene range validation | Implemented |
| Upload-order independence | Implemented |
| Missing Scene reporting | Implemented |
| Duplicate/occupied protection | Implemented |
| Invalid file reporting | Implemented |
| Scene review and final clip order | Implemented |
| Refresh restoration | Implemented |
| Project-aware 2x2 destinations | Implemented in AIR-0109 |
| Deterministic crop filenames | Implemented in AIR-0109 |
| Direct crop-to-Scene import | Implemented in AIR-0109 |
| Manual Scene replacement | Implemented |
| Unmatched stored-asset assignment board | Not implemented |
| Version history/rollback | Not implemented |
| Chunked/resumable upload | Not implemented |
| Canonical backend `assets_ready` state | Implemented in AIR-0112 |

## Canonical Readiness Contract

AIR-0112 defines policy `image_or_video`:

- every Scene number from 1 through the highest Scene must exist
- every Scene must have a non-empty `image_url` or `video_url`
- duplicate Scene numbers block readiness
- missing Scene-number gaps block readiness
- upload order does not affect canonical Scene order

The backend persists `assets_ready`, `asset_completion_percent`,
`asset_readiness_json`, `assets_ready_at`, and `project_complete`.
`project_complete` requires both ready assets and a terminal project status.
A historical `rendered` value alone no longer proves Scene completeness.

## Priority Fix Order

### P0: Runtime Browser Verification

- verify one real 2x2 grid against a test project
- verify four destination Scene previews
- import into empty slots
- refresh `/image-gen`
- confirm image/video independence and Scene order

### P0: Canonical Readiness

- completed in AIR-0112 with policy `image_or_video`
- backend readiness is persisted and returned through project APIs
- Longform render is blocked with HTTP 409 when readiness fails
- authenticated browser verification remains for AIR-0113

### P1: Unmatched Asset Assignment

- list stored but unlinked assets
- assign them to a Scene without re-upload
- support explicit occupied-slot replacement confirmation

### P2: Large Upload Resilience

- add per-file progress
- add retry/cancel
- evaluate chunked video upload
- avoid holding every large file in memory

## AIR-0110 Handoff

AIR-0110 should browser-verify the complete project-aware crop/import/review flow and formalize the backend `assets_ready` policy.
