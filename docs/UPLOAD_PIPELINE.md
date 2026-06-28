# LONGFORM UPLOAD PIPELINE

## Scope

This document describes the worker-facing media import pipeline on the Longform `image-gen` page.
It is based on the runtime code reviewed for AIR-0107 on 2026-06-28.
Longform Music, Shorts, and Commerce are outside this scope.

AIR Studio creates scene prompts and manages imported assets.
Users create images, upscale images, and create video clips in external services.

## Image Generation Page

Route: `/image-gen?project_id={id}`

Template: `templates/pages/image_gen.html`

Primary data:

- `GET /api/projects/{id}/image-prompts`
- SQLite `image_prompts`
- one row per numbered scene
- `image_url` and `video_url` are independent slots on the same scene

The page renders scenes in the order returned by the backend.
`database.get_image_prompts()` uses `ORDER BY scene_number`, so assigned assets remain in scene order after reload.

## Scene Slot Model

Each scene has:

- `scene_number`
- scene text and title
- image prompt
- video motion prompt
- one active `image_url`
- one active `video_url`

The image and video slots are separate.
An image and video can therefore both belong to Scene 3 without being treated as duplicates.

Current limitation:

- `scene_number` is the identity and display order.
- There is no immutable scene UUID.
- Re-saving all prompts can delete and renumber scene rows.

## Image Upload Flow

### Single Scene

1. The user chooses the upload control on a scene card.
2. The browser sends `project_id`, `scene_number`, and one file to `POST /api/image/upload-scene`.
3. The server stores the file in the project output directory.
4. `database.update_image_prompt_url()` updates the scene's `image_url`.
5. The page reloads or redraws that scene.

Status: Implemented.

Use this path when intentionally replacing an upscaled image.
Single-scene upload is explicit and deterministic, but replacement history is not retained.

### Bulk Images

1. The user selects or drops multiple files on `/image-gen`.
2. The browser posts all files to `POST /api/image/bulk-match`.
3. Supported image types are validated by extension and size.
4. The server tries to parse a scene number from each filename.
5. Files without a scene number are sent to Gemini Vision for semantic matching.
6. Safe assignments update `image_prompts.image_url`.
7. The response returns assignment and validation details.
8. The page redraws the scene list and displays an import result summary.

Status: Implemented with remaining operational limitations.

## Video Upload Flow

### Single Scene

The same scene-card upload control accepts video.
`POST /api/image/upload-scene` writes the file and updates `video_url`.

The legacy endpoint `POST /api/upload-video-to-project/{project_id}/{scene_number}` also supports scene-specific media upload.

Status: Implemented.

### Bulk Video Clips

Bulk video follows the same `/api/image/bulk-match` flow as images.
For unnumbered video files, AIR Studio extracts the middle frame and sends that preview to Gemini Vision.

Status: Implemented with AI fallback dependency.

## 2x2 Image Input and Crop

Route: `/image-crop`

Endpoint: `POST /api/settings/crop-grid`

Current flow:

1. Upload one or more externally generated 2x2 grids.
2. AIR Studio calls the crop endpoint four times per grid.
3. The server divides the image at the horizontal and vertical midpoint.
4. The browser stores the four returned blobs.
5. The user downloads one panel or a ZIP.

Output filename shape:

- `{source}_cropped_top_left.png`
- `{source}_cropped_top_right.png`
- `{source}_cropped_bottom_left.png`
- `{source}_cropped_bottom_right.png`

Status: Crop is implemented; project handoff is not implemented.

The crop page does not receive `project_id`, starting scene, or scene mapping.
The cropped images are not automatically saved into project scene slots.

## Upscaled Image Replacement

Current supported method:

- Upload the final upscaled image through the target scene card.

Status: Implemented as replacement, not as versioned asset management.

Missing:

- original/upscaled relationship
- external service metadata
- replacement history
- rollback

## Automatic Scene Matching

### Deterministic Filename Matching

AIR-0107 added filename-first matching.

Recognized examples:

- `scene_001_upscaled.png` -> Scene 1
- `clip-s12-final.mp4` -> Scene 12
- `003_result.webp` -> Scene 3

Filename matching is authoritative when a supported scene token is present.
Gemini cannot override it.

### AI Fallback

Files without a recognized scene number use Gemini Vision:

- image content is submitted directly
- video uses an extracted middle frame
- project scene descriptions are supplied as matching context

Status: Implemented as fallback.

Risk:

- unnumbered-file matching still depends on Gemini availability and spend capacity
- semantic matching can be wrong and should be reviewed by the user

## Validation Contract

`POST /api/image/bulk-match` now returns:

- `matched`
- `unmatched`
- `duplicates`
- `invalid`
- `missing_scenes.images`
- `missing_scenes.videos`
- refreshed `scenes`

### Duplicate Handling

Bulk upload does not overwrite:

- an existing image in the same scene image slot
- an existing video in the same scene video slot
- a slot already claimed by another file in the same upload

These files are reported under `duplicates`.

Status: Implemented for bulk upload.

Single-scene upload still intentionally replaces the active slot.

### Invalid File Handling

Reported as invalid:

- unsupported extension
- file larger than the configured image/video limit
- parsed or AI-provided scene number outside the project scene range
- malformed scene number returned by matching

Status: Implemented.

Valid media that cannot be assigned may remain in the project output directory as an unlinked asset.
Automatic cleanup is not implemented.

### Missing Scene Handling

After safe assignments, the endpoint reports every scene without:

- an image
- a video

The page displays those scene numbers in the import summary.

Status: Implemented as reporting.

It does not yet block workflow advancement because some scenes may intentionally use only an image.

## Upload Progress

Current UI behavior:

- loading state is shown while files upload and match
- selected file count is shown in the status text
- final counts and issue details are shown after completion

Status: Partially implemented.

Missing:

- transferred bytes
- per-file progress
- per-file upload/matching stage
- cancel and retry controls

## Current Implementation Summary

| Capability | Status |
| --- | --- |
| Scene list and image/video slots | Implemented |
| Single image upload/replacement | Implemented |
| Single video upload/replacement | Implemented |
| Mixed multi-file upload | Implemented |
| Filename-first scene matching | Implemented in AIR-0107 |
| Gemini fallback matching | Implemented |
| Scene order after upload | Implemented |
| Duplicate/occupied slot protection | Implemented for bulk upload |
| Out-of-range/invalid reporting | Implemented |
| Missing scene report | Implemented |
| Final result summary UI | Implemented |
| 2x2 grid crop | Implemented |
| Crop-to-project scene handoff | Not implemented |
| External upscaling provenance | Not implemented |
| Per-file upload progress | Not implemented |
| Asset version history/rollback | Not implemented |

## Improvement Priority

### P0: Project-aware 2x2 handoff

- Open crop with `project_id`.
- Select the first target scene.
- Produce deterministic scene filenames.
- Preview four scene assignments before upload.
- Import the panels directly into empty image slots.

### P1: Import review and correction

- Let the user reassign unmatched files without re-uploading.
- Let the user explicitly approve replacement of occupied slots.
- Add cleanup for rejected or abandoned stored files.

### P1: Scene identity protection

- Prevent prompt regeneration from renumbering scenes with assigned media.
- Introduce immutable scene identity if reorder support is required.

### P2: Better progress

- Add per-file progress and retry.
- Separate upload, preview extraction, AI matching, and database assignment states.

## Needs Verification

- Browser-level test with real mixed image/video files on the primary 8001 runtime.
- Large-file behavior through the packaged desktop runtime.
- Exact user-facing Vietnamese and Thai wording for the new result summary.
- Whether final production requires both image and video for every scene or permits intentional image-only scenes.
