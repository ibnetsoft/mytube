# LONGFORM SCENE ASSET REVIEW

## Scope

This document records the AIR-0108 review of uploaded Longform scene assets.
It covers the point after external images and video clips have been imported and before the worker continues to narration, subtitles, assembly, and export.

## Review Surface

Route: `/image-gen?project_id={id}`

Template: `templates/pages/image_gen.html`

Source of truth:

- `GET /api/projects/{id}/image-prompts`
- SQLite `image_prompts`
- rows ordered by `scene_number`

AIR-0108 adds a `Scene Asset Review` section above the detailed scene cards.
The section is rebuilt whenever prompt/asset data is loaded or redrawn.

## Verification Results

### 1. Image Match Per Scene

Status: Implemented.

- Every scene row shows `Image ready` or `Image missing`.
- The detailed scene card shows the imported image.
- The review count shows how many scenes have images.

### 2. Video Clip Match Per Scene

Status: Implemented.

- Every scene row shows `Video ready` or `Video missing`.
- The review count shows how many scenes have video clips.
- Uploaded clips are listed separately under `Final clip order`.

### 3. Scene Order

Status: Implemented.

- Backend retrieval uses `ORDER BY scene_number`.
- The review panel sorts by `scene_number`.
- The final clip list follows the same scene order.

### 4. Missing Scenes

Status: Implemented as a review gate.

- A scene with neither image nor video is counted as `Missing visual`.
- The Continue button is disabled until every scene has at least one visual asset.
- Missing video clips are listed separately because an image-only scene may still be intentional.

Needs product decision:

- Whether final production requires a video for every scene.
- Whether image-only scenes should always satisfy readiness.

### 5. Duplicate Files

Status: Implemented during bulk upload, not persisted as history.

- AIR-0107 reports duplicate and occupied-slot files in the upload result.
- AIR-0108 review shows the final active asset per slot.
- Duplicate attempt history disappears after refresh because it is not stored in SQLite.

TODO:

- Persist import audit history only if operators need later duplicate investigation.

### 6. Replace Incorrect Matches

Status: Implemented.

- `View` scrolls to the detailed scene card.
- `Replace` opens that scene's file input.
- The existing asset library can also assign a stored file to the selected scene.

AIR-0108 fixed a destructive UI bug:

- uploading a video no longer clears the scene image
- uploading an image no longer clears the scene video
- choosing an asset from the library no longer clears the opposite media slot

Image and video now remain independent as defined by the database contract.

Remaining:

- no version history or rollback
- no manual drag/drop reassignment between scene rows

### 7. Prompt and Asset Together

Status: Implemented.

- The compact review row shows a prompt excerpt beside image/video status.
- `View` opens the existing detailed card where the full image prompt, video prompt, scene text, and media are available together.

### 8. Final Clip List

Status: Implemented.

- Only scenes with `video_url` appear in `Final clip order`.
- Each entry is labeled by scene number and links to the stored clip.
- Missing video scene numbers are shown below the list.

### 9. Move to Final Production Stages

Status: Partially implemented by the canonical workflow.

- When all scenes have at least one visual asset, the worker can continue to `/tts?project_id={id}`.
- The correct Longform sequence remains TTS -> subtitles -> render -> export.
- AIR-0108 does not add an unsafe direct jump from image review to export.

Needs verification:

- Define one backend-owned `assets_ready` state.
- Confirm the final render page consumes both image-only and video scenes as expected.

### 10. Refresh Persistence

Status: Implemented for active matches.

- `image_url` and `video_url` are persisted in SQLite.
- Project restoration and the image-prompts endpoint reload those values.
- The review section is rebuilt from restored backend data.

Not persisted:

- duplicate upload attempts
- unmatched-file review decisions
- review approval timestamp

## Readiness Rule

AIR-0108 uses this minimum UI rule:

```text
ready_to_continue = every scene has image_url OR video_url
```

Video absence is a warning, not a blocker, because the current product contract has not decided whether image-only scenes are allowed.

This is intentionally a UI gate, not a canonical project status.

## Current Gaps

1. No backend `assets_ready` state.
2. No persisted review approval or reviewer identity.
3. No asset version history or rollback.
4. Duplicate/unmatched attempt history is not retained after refresh.
5. No manual reassignment board for already stored unmatched files.
6. No browser-level verification with a real mixed-media project on port 8001 in this task.

## AIR-0109 Priority

1. Connect 2x2 crop output to explicit project scene slots.
2. Reuse occupied-slot and duplicate protection.
3. Add manual assignment for stored unmatched assets.
4. Decide and implement the canonical `assets_ready` policy.
5. Browser-verify image-only, video-only, mixed, missing, replacement, refresh, and TTS transition cases.
