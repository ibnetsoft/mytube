# AIR STD Web Admin/API Alignment

Date: 2026-08-14

## Decision

The STD web service must not introduce a separate admin surface. It should use the current web admin data contracts so installed desktop STD users and web STD users can operate at the same time.

Removed:
- `/admin/std`
- `/api/admin/std-projects/**`

Kept as web-only implementation detail:
- `std_projects`
- `std_project_scenes`
- `std_project_assets`
- `std_project_submissions`

Compatibility bridge added:
- `auth-web/lib/stdLegacySync.ts`
- `auth-web/lib/stdRecommendations.ts`
- `auth-web/lib/stdRenderQueue.ts`

## Existing Desktop App Contracts

The installed app goes through `services/web_admin_client.py` and related routers.

Primary web-admin bridge endpoints:
- `/api/desktop-login`
- `/api/desktop-resync`
- `/api/desktop-topics-bridge`
- `/api/desktop-project-sync`
- `/api/desktop-drive-token`
- `/api/desktop-render-queue`
- `/api/desktop-profile-update`
- `/api/desktop-change-password`
- `/api/desktop-referrals`
- `/api/desktop-support`
- `/api/desktop-announcements`

Main topic claim path:
- Desktop route: `app/routers/user_topics.py::claim_topic`
- Auth-web bridge: `/api/desktop-topics-bridge`, action `claim_topic`
- Shared table: `topics_queue`
- Claim state:
  - `topics_queue.status = assigned`
  - `topics_queue.assigned_employee_email = verified email`
  - `topics_queue.assigned_at = now`

Project sync path:
- Desktop service: `services/project_sync_service.py`
- Auth-web bridge: `/api/desktop-project-sync`
- Shared table: `desktop_project_metadata`
- Key fields:
  - `sync_id`
  - `employee_email`
  - `name`
  - `topic`
  - `status`
  - `language`
  - `app_mode`
  - `project_payload`
  - `progress_payload`

Render/admin path:
- Desktop service: `services/remote_drive_render_service.py`
- Auth-web bridge: `/api/desktop-render-queue`
- Shared table: `remote_render_queue`
- Admin route: `/api/admin/render-queue`

Publishing path:
- Shared table: `publishing_requests`
- Admin route: `/api/admin/publishing`

## Current Web Admin Expectations

The current main admin UI is `auth-web/components/DashboardContent.tsx`.

Important tabs:
- `topics-queue`: reads `/api/admin/topics-queue`
- `render-queue`: reads `/api/admin/render-queue`
- publishing requests: reads `/api/admin/publishing`
- users/categories/styles/global settings: existing admin APIs

The `topics-queue` tab uses:
- `topics_queue.status`
- `topics_queue.assigned_employee_email`
- `topics_queue.pregenerated_structure_status`
- `topics_queue.pregenerated_script_status`
- `topics_queue.publish_metadata` or `topics_queue.progress_payload.publish_metadata`
- `topics_queue.progress_payload.steps`
- `topics_queue.progress_payload.project_status`
- `topics_queue.progress_updated_at`

## Web STD Compatibility Layer

`syncStdProjectToLegacy(projectId)` now writes web STD state into the existing contracts:

1. Upserts `desktop_project_metadata`
   - `sync_id = std-web-{std_projects.id}`
   - `employee_email = std_projects.employee_email`
   - `project_payload` shaped like desktop project sync payload
   - `progress_payload` shaped like desktop progress snapshots

2. Updates `topics_queue`
   - `progress_payload`
   - `progress_updated_at`

Call sites:
- STD topic claim
- STD asset upload complete
- STD project submit

STD topic recommendation now mirrors the installed app's `/api/user/recommended-topics` scoring model:
- assigned employee match: +50
- preferred language: +30
- preferred duration bucket: +25
- preferred category: +20
- new topic within 24h: +10
- `user_topic_recommendations` cache is read and refreshed.

STD submit now creates a row in the existing `remote_render_queue` table:
- `render_mode = std_web_drive_assets`
- `job_type = std_web_render`
- `asset_file_id` points to a Google Drive JSON manifest.
- `project_id = 1000000000 + topic_queue_id`
- `topics_queue.local_project_id` is set to that same pseudo project id so existing admin joins can still find the topic row.

## Remaining Work

Highest priority:
- Add worker-side support for `remote_render_queue.job_type = std_web_render`.
  - Existing legacy Drive worker only claims `render_mode = drive_api` and expects a ZIP asset package.
  - Web STD intentionally submits `render_mode = std_web_drive_assets` so the legacy ZIP worker will not accidentally claim and fail it.
  - The queued manifest contains Drive file IDs for every scene image/video.

Risk:
- `topics_queue.local_project_id` is integer-oriented for desktop local project IDs. Web STD writes a pseudo id of `1000000000 + topic_queue_id`; this avoids UUID/integer mismatch but should be treated as a reserved web range.
- Existing admin code joins render rows to `topics_queue.local_project_id`; this is why the pseudo id is written at submit time.
