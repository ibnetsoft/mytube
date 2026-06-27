# LONGFORM USER FLOW

## Scope
- This document describes the current end-to-end worker flow for `Longform Mode` only.
- `longform_music`, `general_shorts`, and `shorts_commerce` are out of scope for this document.
- The goal is to record the real runtime flow as implemented today, not an ideal future design.

## Flow Summary
1. Login
2. Recommended Topics
3. Claim Topic
4. Project Creation
5. Script Plan
6. Script Generation
7. Image Generation
8. Voice Generation
9. Video Generation
10. Export / Delivery

---

## 1. Login

### Purpose
- Authenticate an approved worker and persist worker language/session context before entering the longform workspace.

### Screen / Route
- Page: `/login`
- Post-login landing: `/projects`

### Called API
- `POST /api/auth/login`

### BFF Endpoint
- `app/routers/auth.py::post_auth_login`
- `app/routers/pages.py::page_projects`

### Related DB Tables / Fields
- Supabase `profiles`
  - `email`
  - `password`
  - `pin_code`
  - `is_approved`
- Local cookie/session state
  - `user_email`
  - `language`

### State
- Auth state is cookie-based in the local runtime.
- No local project state is created at this step.

### Next on Success
- Redirect or navigate to `/projects`.

### Failure Handling
- Reject unapproved users.
- Reject wrong password.
- Return `success: false` when Supabase is unavailable or lookup fails.

### Current Implementation
- Implemented.
- Password check currently uses `profiles.password`, then falls back to `pin_code`, then default handling in code.

### TODO
- Needs verification: whether the login contract should continue to rely on direct profile password fields in Supabase.
- Needs cleanup: visible mojibake remains in some auth-facing strings.

---

## 2. Recommended Topics

### Purpose
- Show worker-personalized longform topics that can be claimed and converted into a local project.

### Screen / Route
- Page: `/projects?view=topics`
- Template: `templates/pages/projects.html`

### Called API
- `GET /api/user/recommended-topics`
- `POST /api/user/recommended-topics/translations`
- `GET /api/settings`

### BFF Endpoint
- `app/routers/user_topics.py::get_recommended_topics`
- `app/routers/user_topics.py::translate_recommended_topics`
- `app/routers/settings.py` settings endpoints via `main.py`

### Related DB Tables / Fields
- Supabase `topics_queue`
  - `id`
  - `topic`
  - `status`
  - `employee_email`
  - `category_id`
  - `language`
  - `assigned_duration_minutes`
  - `recommended_duration_minutes`
  - `estimated_payout`
  - `assigned_script_style`
  - `assigned_image_style`
  - `duration_reason`
  - `difficulty_level`
- Supabase `categories`
  - `id`
  - `name`
  - `language`
  - `default_script_style`
  - `default_image_style`
  - `video_type` (currently expected by runtime, but missing in deployed schema for music-mode use)
- Supabase `user_topic_recommendations`
  - `id`
  - `topic_queue_id`
  - `employee_email`
- Supabase `global_settings`
  - longform payout/duration policy keys
- Supabase `payout_rebalancing_settings`
  - payout multiplier inputs

### State
- Topic queue state: primarily `pending` before claim.
- UI filter state:
  - duration filter
  - language filter
  - current UI language
- Translation state is partially dynamic and can trigger fallback providers.

### Next on Success
- Worker chooses a recommendation card and proceeds to claim.

### Failure Handling
- Empty list returns a normal empty state.
- Translation failures can fall back or return untranslated values.
- Supabase fetch failure returns HTTP 500 from the BFF.

### Current Implementation
- Implemented.
- Recommendation payload already includes fixed longform metadata used by the cards:
  - duration
  - payout
  - script style
  - image style

### TODO
- Reduce language-switch and translation latency on this page.
- Prefer saved/cached translations over repeated provider calls.
- Needs verification: whether duplicate cards should be deduplicated before render.

---

## 3. Claim Topic

### Purpose
- Atomically assign a selected topic to the current worker and start a local project with locked admin-defined policy values.

### Screen / Route
- Triggered from `/projects?view=topics`

### Called API
- `POST /api/user/claim-topic`

### BFF Endpoint
- `app/routers/user_topics.py::claim_topic`

### Related DB Tables / Fields
- Supabase `topics_queue`
  - `id`
  - `status` (`pending` -> `assigned`)
  - `employee_email`
  - `category_id`
  - `language`
- Supabase `user_topic_recommendations`
  - `id`
  - `topic_queue_id`
- Local `projects`
  - new project row created at claim time
- Local `project_settings`
  - `topic_queue_id`
  - `topic_queue_category_id`
  - `target_language`
  - `script_style`
  - `image_style`
  - `style_locked`
  - `duration_seconds`
  - `assigned_duration_minutes`
  - `assigned_duration_seconds`
  - `duration_locked`
  - `estimated_payout`
  - `duration_reason`
  - `difficulty_level`
  - `payout_policy_json`
  - channel preference fields when category upload defaults are applied

### State
- Supabase topic state changes to `assigned`.
- Local project mode is derived from category `video_type`, with fallback to `longform`.
- Local style and duration lock flags are enabled for longform claims.

### Next on Success
- Browser redirects to `/script-plan?project_id={id}&auto=true&topic=...`
- In `Longform Mode`, claim success must not route the worker into `/music-plan`.

### Failure Handling
- `401` when not authenticated.
- `404` when the recommendation/topic cannot be resolved.
- `500` when Supabase claim update fails.
- Frontend restores card state and reloads recommendations on failure.

### Current Implementation
- Implemented for `longform`.
- Backward compatibility exists for stale recommendation IDs by resolving `user_topic_recommendations.id` to `topic_queue_id`.
- Frontend claim success already routes by returned `project_mode`, so `longform` claims go to `/script-plan` and only `longform_music` claims go to `/music-plan`.

### TODO
- Needs verification: enforce stronger claim atomicity if multiple workers can race on the same `topics_queue` row.
- Deferred-mode blocker: real `longform_music` claim routing cannot be validated until deployed `categories.video_type` exists.

---

## 4. Project Creation

### Purpose
- Materialize the claimed topic as a local longform project with runtime settings that downstream pages can use.

### Screen / Route
- Indirect step during claim flow.
- Worker reaches the created project through `/script-plan?project_id=...`

### Called API
- No separate browser call beyond `POST /api/user/claim-topic` in the recommendation path.
- Manual fallback project creation also exists via `POST /api/projects`.

### BFF Endpoint
- `app/routers/user_topics.py::claim_topic`
- local helper `database.py::create_project`
- manual create path: `app/routers/projects.py::create_project`

### Related DB Tables / Fields
- Local `projects`
  - `id`
  - `name`
  - `topic`
  - `status`
  - `language`
  - `employee_email`
- Local `project_settings`
  - `app_mode`
  - `target_language`
  - `script_style`
  - `image_style`
  - longform lock/payout fields listed above

### State
- New local project row is created with default project status from SQLite schema.
- In current schema, `projects.status` defaults to `draft`.
- Longform step UIs later move the project through `planned`, `scripted`, `tts_done`, `rendered`, and related downstream states.

### Next on Success
- Use the new `project_id` as the active workspace context.

### Failure Handling
- Claim call fails as a whole if local project creation cannot complete.

### Current Implementation
- Implemented.
- Local creation already stores `app_mode`, `target_language`, `script_style`, and `image_style`.

### TODO
- Needs verification: standardize whether all longform projects should stay `draft` at creation or move immediately to a more explicit claimed/bootstrapped state.

---

## 5. Script Plan

### Purpose
- Build the content structure before script generation and persist the locked topic context plus editable structure.

### Screen / Route
- Page: `/script-plan?project_id={id}`
- Template: `templates/pages/script_plan.html`

### Called API
- `GET /api/projects/{id}/full`
- `GET /api/projects/{id}/script-structure`
- `POST /api/projects/{id}/script-structure`
- `GET /api/projects/{id}/metadata`
- `POST /api/projects/{id}/settings`
- `PATCH /api/projects/{id}`
- `POST /api/gemini/generate-structure`
- Optional source APIs:
  - `GET /api/projects/{id}/sources`
  - `POST /api/projects/{id}/sources/url`
  - `POST /api/projects/{id}/sources/file`

### BFF Endpoint
- `app/routers/pages.py::page_script_plan`
- `app/routers/projects.py::get_project`
- `app/routers/projects.py::get_script_structure`
- `app/routers/projects.py::save_script_structure`
- metadata/settings endpoints in `main.py`

### Related DB Tables / Fields
- Local `projects`
  - `id`
  - `topic`
  - `status`
- Local `project_settings`
  - `duration_seconds`
  - `assigned_duration_minutes`
  - `duration_locked`
  - `script_style`
  - `image_style`
  - `style_locked`
  - `target_language`
- Local `script_structure`
  - `hook`
  - `sections`
  - `cta`
  - `style`
  - `duration`
- Local `project_sources`
  - `source_type`
  - `title`
  - `content`
  - `url`

### State
- Stepper treats this as the planning stage.
- On successful structure generation/save, the UI sets project status to `planned`.
- Style and duration lock rules are enforced by settings endpoints for longform claims.

### Next on Success
- Move to `/script-gen?project_id={id}`

### Failure Handling
- Missing project or structure returns empty/loading states.
- AI structure generation failures surface toasts and do not advance status.
- Locked settings reject edits to protected fields.

### Current Implementation
- Implemented.
- Browser verification from prior tasks confirmed claimed longform projects load with topic title and locked metadata on this page.
- Route is now project-aware: `/script-plan` only redirects to `/music-plan` when the selected project's actual mode is `longform_music`.

### TODO
- Needs verification: apply the same project-aware mode resolution consistently across the rest of the longform/music page family, not only plan routing.

---

## 6. Script Generation

### Purpose
- Generate and persist the full longform script from the saved plan.

### Screen / Route
- Page: `/script-gen?project_id={id}`
- Template: `templates/pages/script_gen.html`

### Called API
- `GET /api/projects/{id}/full`
- `POST /api/projects/{id}/script`
- `GET /api/projects/{id}/script`
- `POST /api/projects/{id}/translate-script`
- Optional automation queue APIs:
  - `POST /api/autopilot/continue/{id}`
  - `GET /api/projects/{id}/queue`

### BFF Endpoint
- `app/routers/pages.py::page_script_gen`
- script save/get endpoints in `main.py`

### Related DB Tables / Fields
- Local `scripts`
  - `full_script`
  - `word_count`
  - `estimated_duration`
- Local `project_settings`
  - `script`
  - `script_vi` and translation-related derived fields
- Local `projects`
  - `status`

### State
- On script save, runtime updates project status to `scripted`.
- Script content also becomes input for image, TTS, subtitle, and render stages.

### Next on Success
- Usually proceed to `/image-gen?project_id={id}` and later `/tts`.

### Failure Handling
- Missing structure blocks useful generation.
- Save or generation failure keeps the project in the prior stage and shows an error.

### Current Implementation
- Implemented.

### TODO
- Needs verification: there is no single documented source of truth for when manual edits vs AI generation should update the final script status.

---

## 7. Image Generation

### Purpose
- Convert script scenes into image prompts, asset metadata, and scene-level video/image inputs for rendering.

### Screen / Route
- Page: `/image-gen?project_id={id}`
- Template: `templates/pages/image_gen.html`

### Called API
- `GET /api/settings`
- `POST /api/image/generate-dual-prompts`
- `POST /api/projects/{id}/image-prompts`
- `GET /api/projects/{id}/image-prompts`
- `POST /api/projects/{id}/analyze-scenes`
- `POST /api/projects/{id}/generate-video`
- Optional character/scene helpers:
  - `GET/POST /api/projects/{id}/characters`
  - `POST /api/projects/{id}/scenes/animate`

### BFF Endpoint
- `app/routers/pages.py::page_image_gen`
- image/video helper endpoints across `main.py`, `app/routers/projects.py`, `app/routers/image.py`

### Related DB Tables / Fields
- Local `image_prompts`
  - `scene_number`
  - `scene_text`
  - `prompt_ko`
  - `prompt_en`
  - `image_url`
  - `video_url`
  - `motion_desc`
  - `flow_prompt`
  - `scene_type`
- Local `project_characters`
- Local `project_settings`
  - `image_style`
  - `visual_style`
  - scene-level derived asset paths

### State
- This stage does not appear to advance a single canonical `projects.status` value by itself in the normal longform path.
- Completion is inferred in the UI from saved prompt/image/video data.

### Next on Success
- Proceed to `/tts?project_id={id}` after scene assets are prepared.

### Failure Handling
- Missing script or prompt-generation failures surface errors and keep the user on the page.
- Scene-level video generation can fail per scene without necessarily invalidating the whole project.

### Current Implementation
- Implemented, but state ownership is partly data-driven rather than status-driven.

### TODO
- Needs verification: define a clearer canonical status transition for "image prep complete" if downstream orchestration needs it.

---

## 8. Voice Generation

### Purpose
- Generate narration audio and store TTS output plus alignment data for subtitles and final render.

### Screen / Route
- Page: `/tts?project_id={id}`
- Template: `templates/pages/tts.html`

### Called API
- `GET /api/projects/{id}/full`
- `GET /api/projects/{id}/settings`
- `POST /api/projects/{id}/settings`
- `GET /api/projects/{id}/script`
- `POST /api/tts/generate`
- `GET /api/tts/voices`
- `POST /api/projects/{id}/tts/upload`
- `POST /api/projects/{id}/generate-tts-scenes`

### BFF Endpoint
- `app/routers/pages.py::page_tts`
- TTS endpoints in `main.py`
- scene TTS endpoint in `app/routers/projects.py::generate_tts_scenes`

### Related DB Tables / Fields
- Local `tts_audio`
  - `voice_id`
  - `voice_name`
  - `audio_path`
  - `duration`
- Local `project_settings`
  - `voice_provider`
  - `voice_name`
  - `voice_language`
  - `voice_speed`
  - `voice_mapping_json`
  - `tts_word_alignment`
  - `scene_{n}_audio_path`
- Local `projects`
  - `status`

### State
- Successful TTS save/upload updates project status to `tts_done`.

### Next on Success
- Proceed to `/subtitle-gen?project_id={id}`

### Failure Handling
- Missing script blocks narration generation.
- Provider-specific generation failures return errors and may produce partial scene results.

### Current Implementation
- Implemented.
- Language-aware provider selection exists in the runtime.

### TODO
- Needs verification: unify full-audio and per-scene TTS completion rules under one clearer completion contract.

---

## 9. Video Generation

### Purpose
- Produce the final longform video package from script, images, optional intro, subtitles, and audio.

### Screen / Route
- Intro/scene prep page: `/video-gen?project_id={id}`
- Subtitle page: `/subtitle-gen?project_id={id}`
- Render page: `/render?project_id={id}`

### Called API
- Intro page:
  - `GET /api/projects/{id}/intro`
  - `GET /api/projects/{id}/intro/plan`
  - `GET /api/projects/{id}/intro/bgm`
  - `POST /api/projects/{id}/intro/save`
- Subtitle page:
  - subtitle generation/save endpoints under `app/routers/video.py`
- Render page:
  - `POST /api/project/{id}/render-queue`
  - `GET /api/project/{id}/render/status`
  - `GET /api/render-queue`
  - `POST /api/projects/{id}/render` (used by page logic)

### BFF Endpoint
- `app/routers/pages.py::page_video_gen`
- `app/routers/pages.py::page_subtitle_gen`
- `app/routers/pages.py::page_render`
- render/subtitle endpoints in `main.py` and `app/routers/video.py`

### Related DB Tables / Fields
- Local `project_settings`
  - `intro_video_path`
  - `background_video_url`
  - `subtitle_path`
  - `image_timings_path`
  - `timeline_images_path`
  - `image_effects_path`
  - `video_path`
  - `qa_status`
  - `qa_hold_upload`
  - `qa_result_json`
  - payout result fields:
    - `actual_payout`
    - `video_clip_ratio`
    - `total_scenes`
    - `video_scenes`
    - `image_scenes`
    - `asset_mix_summary_json`
- Local `projects`
  - `status`

### State
- Render queue entry can move the project through:
  - `tts_done`
  - `remote_packaging` / `remote_queued` in some render paths
  - `rendered`
  - `completed` in downstream logic
- UI step completion also checks presence of render outputs like `video_path`.

### Next on Success
- Proceed to export/delivery from `/video-upload?project_id={id}`.

### Failure Handling
- Render queue or asset preparation errors return explicit errors.
- QA hold can block downstream publish/upload paths.

### Current Implementation
- Implemented.
- Status handling is partly split between local render, remote queue sync, and UI inference.

### TODO
- Needs verification: define whether `rendered` or `completed` is the canonical terminal render state for longform workers.

---

## 10. Export / Delivery

### Purpose
- Hand off the finished longform video for publish or external delivery.

### Screen / Route
- Page: `/video-upload?project_id={id}`
- Template: `templates/pages/video_upload.html`

### Called API
- `GET /api/projects/{id}/drive-bundle`
- `POST /api/projects/{id}/admin-publish-request`
- `POST /api/youtube/upload-external/{id}`
- `POST /api/projects/{id}/youtube/auto-upload`
- `POST /api/projects/{id}/youtube/public`
- Optional learning/logging helpers also run from this page

### BFF Endpoint
- `app/routers/pages.py::page_video_upload`
- delivery/upload endpoints in `main.py`
- additional upload logic also exists in `app/routers/video.py`

### Related DB Tables / Fields
- Local `project_settings`
  - `external_video_path`
  - `video_path`
  - `is_uploaded`
  - `youtube_video_id`
  - `upload_source`
  - `admin_publish_ready`
  - `admin_publish_status`
  - `preferred_youtube_channel_handle`
  - `preferred_youtube_channel_name`
  - `youtube_channel_id`
- Local `project_learning_events`
- Local `project_learning_snapshots`
- Local `projects`
  - terminal states used elsewhere include `uploaded` and `youtube_published`, but this needs runtime verification in the current worker path

### State
- Delivery can end in:
  - admin publish registration flow
  - local/external YouTube upload flow
  - uploaded flags without a single canonical worker-facing terminal status
- `is_uploaded=1` is used by the UI regardless of whether the path is admin-managed or direct upload.

### Next on Success
- Operationally complete from the worker perspective.
- Admin-side publishing may continue after this point.

### Failure Handling
- Standard worker accounts are blocked from some direct local YouTube upload paths and must use web-admin publishing registration.
- Missing rendered video or metadata blocks publish request registration.

### Current Implementation
- Implemented, but split across multiple delivery paths.
- `Longform Music` workflow is treated as an internal-only mode and should not be the default path for standard online `Longform Mode` workers.

### TODO
- Needs verification: define one canonical longform worker export contract.
- Needs verification: decide whether standard workers should only use `admin-publish-request` and never see direct upload controls.

---

## Cross-Cutting Notes

### BFF Shape
- AIR Studio is effectively using the Python runtime as the worker-facing BFF.
- Frontend templates call local `/api/...` endpoints directly.
- Those BFF routes fan out to:
  - local SQLite via `database.py`
  - Supabase via `web_admin_client` / direct requests
  - AI providers and render services

### Local Project Statuses Seen In Code
- `draft`
- `planned`
- `scripted`
- `tts_done`
- `remote_packaging`
- `remote_queued`
- `rendered`
- `completed`
- `uploaded`
- `youtube_published`

### Longform-Specific Locking Already In Use
- `style_locked`
- `duration_locked`
- `assigned_duration_minutes`
- `estimated_payout`

### Main Gaps Found During Documentation
1. Project status progression is real but not fully normalized across every stage.
2. Export/delivery has multiple valid paths and no single documented terminal state.
3. Recommendation translation remains a performance-sensitive runtime path.
4. Deferred-mode schema (`categories.video_type`) is still incomplete in the deployed Supabase environment.
