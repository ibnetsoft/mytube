# LONGFORM PRODUCTION PIPELINE

## Scope

This document audits the real `Longform Mode` production pipeline as implemented in AIR Studio on 2026-06-28.
It does not describe `longform_music`, `general_shorts`, or `shorts_commerce`.

AIR Studio is not the production image or video AI service in this workflow.
Its responsibility is to prepare prompts, preserve scene ownership, accept externally produced assets, and keep those assets ordered for the final project.

## Responsibility Boundary

### AIR Studio AI

- Create the script plan.
- Generate the full script.
- Split the script into numbered scenes.
- Generate the image prompt for each scene.
- Generate the video-motion prompt for each scene.

### User

- Copy prompts to an external image AI service.
- Generate 2x2 image grids externally.
- Bring the grids back to AIR Studio and split them into four images.
- Upscale the selected images using an external service.
- Generate video clips using an external video AI service.
- Upload the resulting image and video assets to AIR Studio.
- Review scene assignment and final order.

### External AI Services

- Image generation.
- Image upscaling.
- Video clip generation.

AIR Studio currently contains legacy image/video generation endpoints and controls. They are not the target production contract for online Longform workers and should not be treated as proof that the external workflow is complete.

## End-to-End Workflow

| Step | Owner | Current route or data | Status |
| --- | --- | --- | --- |
| 1. Select topic | AIR Studio | `/projects?view=topics`, `POST /api/user/claim-topic` | Implemented |
| 2. Generate script plan | AIR Studio AI | `/script-plan`, project structure APIs | Implemented |
| 3. Generate script | AIR Studio AI | `/script-gen`, project script APIs | Implemented |
| 4. Split into scenes | AIR Studio AI | `/image-gen`, prompt generation creates numbered scene rows | Partially implemented |
| 5. Create image prompts | AIR Studio AI | `image_prompts.prompt_ko`, `prompt_en` | Implemented |
| 6. Create video prompts | AIR Studio AI | `image_prompts.motion_desc`, `flow_prompt` | Implemented |
| 7. Generate 2x2 images | User + external image AI | Outside AIR Studio | External/manual |
| 8. Open image crop | User | `/image-crop` | Implemented |
| 9. Split each grid into four images | AIR Studio utility | `POST /api/settings/crop-grid` | Implemented, project-disconnected |
| 10. Upscale images | User + external upscaler | Outside AIR Studio | External/manual, untracked |
| 11. Generate clips | User + external video AI | Outside AIR Studio | External/manual |
| 12. Bulk upload clips/images | User | `/image-gen`, `POST /api/image/bulk-match` | Partially implemented |
| 13. Match assets to scenes | AIR Studio AI | Gemini Vision matching into `image_prompts` | Partially implemented |
| 14. Review in scene order | User | `/image-gen`, `GET /api/projects/{id}/image-prompts` | Implemented with validation gaps |

## Implementation Audit

### Topic, Plan, and Script

Status: Implemented.

- A claimed longform topic creates a local project and redirects to `/script-plan`.
- The project stores locked topic policy such as language, script style, image style, assigned duration, and payout.
- Script plan and full script are persisted locally.

Remaining concern:

- The project status contract is not fully normalized across every later production step.

### Scene Splitting

Status: Partially implemented.

- Image-prompt generation derives scene rows from the script.
- `image_prompts.scene_number` is the central scene identity used by the UI and downstream media records.
- Prompt generation asks AI for ordered scene numbers and later normalizes the resulting list.

Structural issue:

- Scene splitting is coupled to image-prompt generation instead of being a separately approved, versioned scene manifest.
- `database.save_image_prompts()` deletes all rows and rewrites `scene_number` as list position (`i + 1`), even if a caller supplied a different scene number.
- Regenerating or reordering prompts can therefore change scene identity and detach the user's mental model from previously exported assets.

### Image Prompt Storage

Status: Implemented.

Primary storage: local SQLite `image_prompts`.

Relevant fields:

- `project_id`
- `scene_number`
- `scene_text`
- `scene_title`
- `prompt_ko`
- `prompt_en`
- `image_url`
- `script_start`
- `script_end`
- `scene_type`

Rows are returned using `ORDER BY scene_number`, so normal page reloads preserve scene order.

### Video Prompt Storage

Status: Implemented.

Relevant fields:

- `motion_desc`
- `flow_prompt`
- `engine`
- `prompt_en_start`
- `prompt_en_end`
- `video_url`

The image-generation page can create and edit motion/Flow prompts per scene.
This fits the intended AI boundary: AIR Studio writes prompts, while the user may generate the actual clip externally.

### 2x2 Image Crop

Status: Implemented as a standalone utility; incomplete as a project workflow.

Current behavior:

- `/image-crop` accepts multiple source grids.
- For each file, the browser calls `POST /api/settings/crop-grid` four times with panel values 1 through 4.
- The server splits at the horizontal and vertical midpoint.
- The user can download individual panels or a ZIP of all results.

Missing production integration:

- The crop page does not know the active project or starting scene number.
- Cropped files are not uploaded directly into `image_prompts`.
- Output filenames do not establish a durable `project_id` + `scene_number` contract.
- There is no handoff from a source grid to the four intended scene numbers.

### Image and Video Upload

Status: Partially implemented.

Single-scene upload:

- `POST /api/image/upload-scene` and `POST /api/upload-video-to-project/{project_id}/{scene_number}` save an image or video and update the corresponding scene row.
- This path is deterministic because the caller supplies the scene number.

Bulk upload:

- `/image-gen` accepts multiple image and video files.
- `POST /api/image/bulk-match` stores all accepted files in the project output directory.
- Videos are represented to the matcher by a middle frame.
- Gemini Vision compares uploaded previews with scene descriptions and returns filename-to-scene mappings.
- Mapped image URLs and video URLs are written into `image_prompts`.

### Automatic Scene Matching

Status: Partially implemented and not production-safe yet.

What works:

- Images and videos can be submitted together.
- Matching can assign files independently of upload order.
- The refreshed scene list is returned after matching.

What is missing:

- No deterministic filename-first rule such as `scene_001.mp4`.
- No validation that a returned scene number exists in the project.
- No one-file-per-scene enforcement.
- The prompt explicitly allows multiple files to map to one scene.
- When multiple files map to the same scene and media type, later updates silently overwrite earlier URLs.
- Matching depends on Gemini availability and spend capacity.
- A failed or unmatched file remains saved in the output directory but is not linked to a scene.

### Order Preservation

Status: Implemented after assignment, fragile before assignment.

- Scene rows load with `ORDER BY scene_number`.
- The UI renders project media in scene order.
- Single-scene uploads retain explicit scene ownership.

Risk:

- AI bulk matching is semantic rather than deterministic.
- Prompt regeneration can renumber all scene rows.
- There is no immutable scene ID separate from display order.

### Missing Scene Handling

Status: Not implemented as a complete user-facing check.

- Empty `image_url` or `video_url` fields technically reveal missing assets.
- The page can display individual empty scene cards.

Missing:

- No preflight summary listing all missing image and video scenes.
- No blocking rule before the workflow advances.
- No explicit bulk-upload result distinguishing matched, unmatched, missing, and invalid files.

### Duplicate Upload Handling

Status: Not implemented safely.

- Re-upload to an explicitly selected scene replaces its current URL.
- Bulk matching can map multiple files to one scene.
- The last database update wins without confirmation.
- Replaced and unmatched physical files are not cleaned up or surfaced as unassigned assets.
- There is no duplicate hash check or version history.

### External Upscaling

Status: External/manual and untracked.

- AIR Studio does not record which image was upscaled, by which service, or from which source version.
- The user can upload the final upscaled image, but provenance is lost.

## Can a Real User Complete the Pipeline Today?

Assessment: Possible with manual care, but not yet reliable enough for routine online-worker production.

A knowledgeable user can:

1. Create plan, script, scenes, and prompts.
2. Generate images and clips externally.
3. Crop 2x2 grids and download results.
4. Upload media per scene or use bulk AI matching.
5. Review media in scene order.

The workflow is fragile because the user must manually carry scene identity across external tools.
The fastest reliable path today is single-scene upload, not bulk AI matching.

## Structural Problems

1. The Longform UI still exposes AIR Studio image/video generation controls even though external generation is the intended operating model.
2. The crop utility is disconnected from project and scene ownership.
3. Scene identity is a mutable sequence number rather than an immutable ID plus display order.
4. Bulk matching is AI-only and has no deterministic filename strategy.
5. Missing, duplicate, overwritten, and unmatched assets are not presented as a validation report.
6. External upscaling provenance is not tracked.
7. There is no canonical `assets_ready` gate before final production stages.

## Priority Fix Order

### P0: Deterministic bulk assignment and validation

- Parse scene numbers from filenames first.
- Use AI matching only for files without a valid scene token.
- Reject out-of-range scene numbers.
- Return explicit `matched`, `unmatched`, `duplicate`, `invalid`, and `missing_scenes` lists.
- Never silently overwrite an occupied scene during bulk upload.

### P0: Production preflight

- Add a project-level scene asset checklist.
- Show missing image and video scenes before advancing.
- Require the user to confirm intentional image-only scenes.

### P1: Project-aware 2x2 crop handoff

- Open crop with `project_id` and a starting scene number.
- Name outputs deterministically.
- Allow the four panels to be assigned or uploaded directly to four scene slots.

### P1: Stabilize scene identity

- Introduce an immutable scene identifier or prevent destructive renumbering after assets exist.
- Preserve existing assets when prompt text is regenerated.

### P2: Align Longform UI with the external-generation contract

- Present prompt copy/export and asset import as the primary controls.
- Hide or clearly mark legacy direct generation controls for internal use.

### P2: Track external asset provenance

- Record source filename, import time, media type, optional external service, and replacement history.

## AIR-0107 Handoff

AIR-0107 should implement the P0 import safety contract first:

1. Deterministic filename-to-scene parsing.
2. Range, duplicate, occupied-slot, and media-type validation.
3. Explicit unmatched and missing-scene response data.
4. UI result summary before any destructive overwrite.
5. Focused tests for order preservation, missing scenes, duplicate files, and mixed image/video upload.
