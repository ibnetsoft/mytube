# Latest Worknote

Date: 2026-06-28
Repo: `C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator`

## Why this file exists
This is the lightweight working memory for AIR Studio. It should explain what we were doing, why it mattered, and what the next session needs to know without reconstructing context from chat.

## Current understanding
- AIR Studio is a local FastAPI application with a substantial worker-facing UI under `templates/`.
- The same repo also includes a Next.js admin app under `auth-web`.
- Recent work has focused on the project page recommendation experience:
  - topic cards
  - translation display
  - payout/duration/style metadata
  - project creation from a topic click

## What changed recently
- Completed AIR-0120 PR #13 documentation cleanup.
- Unified the Longform operation validation taxonomy to `PASS` / `FAIL` / `BLOCKED` only.
- Finalized AIR-0118 in `WORK_INDEX` with commit `47dd2ffb`, PR `#13`, and status `Review Waiting`.
- Confirmed PR #13 remains documentation-only with no runtime code changes.
- Completed AIR-0118 merge handoff for PR #11.
- Confirmed `main` now includes PR #11 at merge commit `0431b723`.
- Created branch `air-0118-longform-operation-validation`.
- Added `docs/LONGFORM_OPERATION_VALIDATION.md` for real Longform operator workflow validation.
- Recorded the 20-step operator scenario with PASS / FAIL / BLOCKED status per stage.
- Confirmed the current run is blocked at authenticated browser execution because safe test credentials were not available.
- Confirmed Longform readiness contract and render gate remain validated by focused tests and code evidence.
- Completed AIR-0116 PR #11 conflict resolution after AIR-0115 / PR #12 merged to main.
- Resolved documentation/status conflicts only.
- Preserved AIR-0112 canonical Longform asset readiness records.
- Preserved AIR-0115 git remote / branch / PR cleanup records.
- Kept PR #11 open for post-conflict review; PR #11 must not be merged without review approval.
- Completed AIR-0115 git remote / branch / PR cleanup.
- Corrected local `origin` from `https://github.com/ibnetsoft/ilddang.git` to `https://github.com/ibnetsoft/mytube.git`.
- Confirmed GitHub CLI is authenticated as `ibnetsoft`.
- Confirmed PR #11 exists in `ibnetsoft/mytube`, is OPEN, and points from `air-0112-longform-e2e-fix-pass` to `main`.
- Confirmed PR #11 commit `f983dcf7` is `AIR-0112 finalize readiness record`.
- Confirmed the earlier PR #11 lookup failure was caused by wrong local remote, not by a missing mytube PR.
- Created AIR-0115 branch from mytube `origin/main` and kept this task documentation-only.
- Completed AIR-0112 canonical Longform asset readiness.
- Formalized the MVP rule: each Scene requires an image or a video.
- Persisted readiness, completion percentage, details, ready timestamp, and
  canonical project completion.
- Added missing Scene-row and duplicate Scene-number validation.
- Added readiness to upload, matching, replacement, restore, and status APIs.
- Blocked incomplete Longform render with HTTP 409.
- Added overall completion and missing Scene numbers to Scene Asset Review.
- Verified project 195 is 18% and incomplete despite historical `rendered`.
- Focused Longform tests: `34 passed, 1 warning`.
- Full tests: `47 passed`; the existing async subtitle test remains uncollected
  without an async pytest plugin.
- Set AIR-0113 to authenticated browser verification.
- Completed AIR-0111 Longform MVP End-to-End validation.
- Classified all 17 worker stages from login through project completion.
- Confirmed the focused Longform suite passes (`29 passed`).
- Confirmed the full suite reaches `42 passed` but has one async pytest
  configuration failure in `tests/test_subtitle.py`.
- Started the integrated runtime and confirmed health on port 8001.
- Reached the login page in the browser; authenticated continuation was blocked
  because no dedicated test credentials were supplied.
- Inspected real SQLite data and found that a project can be `rendered` while
  most Scene assets are missing.
- Set AIR-0112 to create the canonical backend `assets_ready` and
  `project_complete` contract before external Beta.
- Completed AIR-0110A PR cleanup.
- Reconstructed AIR-0106 through AIR-0109 once from current `origin/main`.
- Superseded PR #5, #6, #7, and #8 with one clean integration PR.
- Excluded `36ac3364 feat(air-0001)` and its unrelated Shorts, payout, and database files.
- Preserved AIR-0110 as the next task for real browser verification.
- Completed AIR-0109 Scene Asset upload-pipeline validation.
- Connected `/image-crop` to `project_id` and a starting Scene number.
- Added sequential destination previews for all 2x2 panels.
- Added deterministic `scene_NNN_crop.png` filenames for download, ZIP, and import.
- Added direct import of one panel or all empty Scene image slots.
- Confirmed `scene_NNN_upscaled` images and `scene_NNN` video clips use the same filename-first matcher.
- Documented sequential crop/import performance and large multipart upload risks.
- Completed AIR-0108 Scene Asset Review validation.
- Added a persisted-data review table with prompt, image, and video status per scene.
- Added the final video clip list in scene order.
- Added a minimum readiness gate: every scene needs an image or video before continuing to TTS.
- Fixed scene upload and asset-library replacement so image and video slots no longer clear each other.
- Confirmed active image/video matches restore from SQLite-backed prompt rows after refresh.
- Completed AIR-0107 Longform upload-pipeline validation.
- Added deterministic scene filename parsing before AI matching.
- Kept Gemini Vision as fallback for unnumbered image/video files.
- Prevented silent bulk overwrite of occupied or duplicate image/video slots.
- Added invalid, unmatched, duplicate, and missing-scene response data.
- Added a visible bulk import result summary on `/image-gen`.
- Added `docs/UPLOAD_PIPELINE.md` with the real image, video, crop, replacement, matching, ordering, and progress contracts.
- Verified the matching contract and deterministic upload route with 5 passing tests.
- Audited the full Longform production pipeline under `AIR-0106`.
- Confirmed the target operating model:
  - AIR Studio creates the plan, script, scenes, image prompts, and video prompts
  - users generate images, upscale images, and generate clips in external AI services
  - AIR Studio imports, assigns, orders, and validates the resulting assets
- Added `docs/LONGFORM_PRODUCTION_PIPELINE.md`.
- Confirmed that 2x2 crop works but is disconnected from project scenes.
- Confirmed that mixed image/video bulk upload exists but depends on Gemini semantic matching.
- Found that duplicate scene matches can silently overwrite earlier assignments and unmatched files remain unassigned without a complete user-facing report.
- Fixed the plan-route leak between longform and music workflows:
  - `/script-plan` now resolves from the selected project's real `app_mode` first
  - longform claims stay on `/script-plan`
  - `/music-plan` now rejects non-music projects
  - standard memberships are blocked from entering the music workflow
- Updated `docs/LONGFORM_USER_FLOW.md` to record that longform topic claim success must not route to `/music-plan`.
- Added `docs/LONGFORM_USER_FLOW.md` as the current reference for the `Longform Mode` worker journey:
  - login
  - recommended topics
  - claim-topic
  - project creation
  - script plan
  - script generation
  - image generation
  - voice generation
  - video generation
  - export / delivery
- Documented, from real code paths, the current route/API/BFF/data ownership for each stage.
- Explicitly marked the main unresolved longform contract gaps instead of guessing:
  - canonical status progression is still not fully normalized
  - export/delivery still splits across multiple worker outcomes
  - some stages are inferred from saved assets rather than one backend-owned status
- Added `project_status` + `worknote` scaffolding so future sessions can resume from repo docs.
- Identified that Gemini spend-cap exhaustion is a runtime reliability issue, not a server overload issue.
- Identified a recommendation ID mismatch in the claim flow:
  - recommendation cache rows can have UUID IDs
  - actual claimable records live in `topics_queue`
- Added server-side logic in `app/routers/user_topics.py` to resolve recommendation IDs to `topic_queue_id`.
- Tightened that resolver again for backward compatibility:
  - some open/stale browser tabs can still submit recommendation IDs first
  - the server now checks `user_topic_recommendations.id` before falling back to a raw integer `topics_queue.id`
- Found and fixed another claim-path bug:
  - Supabase topic assignment `PATCH` returns `204`
  - the API treated that as failure because it only accepted `200`
- Removed the native confirmation dialog from topic-card click and replaced it with a simple single-flight guard so the card cannot be double-claimed by repeated clicks.
- Verified runtime with `TestClient`:
  - recommended topics API returns successfully
  - claim-topic API returns `200`
  - created project persists lock/policy values correctly
- Verified in the browser on a fresh server instance (`127.0.0.1:8011`) that:
  1. topic cards render with duration/payout/style metadata
  2. clicking a recommendation card creates a project
  3. redirect lands on `/script-plan`
  4. the plan page loads with the selected topic title populated
  5. verification project created during this run: `project_id=254`, topic queue id `1981`
- Restarted the primary 8001 server completely:
  - stopping only the `main.py` parent was insufficient because its multiprocessing child retained port 8001
  - terminated the old serving child and started a fresh parent/child pair
  - `/api/health` returned `200` from the fresh runtime
- Repeated the full browser flow in the user's logged-in Chrome session on `127.0.0.1:8001`:
  1. recommendation cards loaded with duration, payout, image style, and script style
  2. clicked the unique economy card
  3. claim-topic succeeded
  4. project `256` was created from topic queue id `1937`
  5. redirect landed on `/script-plan`
  6. the page loaded the selected topic and disabled admin-assigned duration/style controls
- Confirmed project `256` in SQLite:
  - `app_mode=longform`
  - `assigned_duration_minutes=15`
  - `estimated_payout=4.0`
  - `script_style=news`
  - `image_style=cinematic`
- Investigated why the music branch could not be exercised:
  - the deployed Supabase `categories` schema has no `video_type` column
  - direct REST selection/filtering of `categories.video_type` returns PostgreSQL `42703`
  - `claim_topic()` currently reads `category.video_type` and defaults missing values to `longform`
  - therefore no current recommendation can resolve to `project_mode=longform_music`

## What still needs verification
1. Normalize canonical longform status progression from claim through export.
2. Decide whether standard workers should end only at `admin-publish-request` instead of mixed upload paths.
3. Apply the same project-aware mode separation to the rest of the longform/music page family.
4. Add/deploy the canonical category mode column and expose it in admin category creation/editing.
5. Seed or generate one pending topic for a `longform_music` category.
6. Run the same browser click verification and confirm `/music-plan` redirect.
7. Decide whether the duplicated recommendation cards currently shown in the grid should be deduplicated server-side or UI-side.
8. Add cooldown/suppression around Gemini spend-cap failures in translation-heavy paths.

## Current longform-focused judgment
- The next meaningful `Longform Mode` improvements are not broad feature additions.
- The best return now is:
  1. fix language-switch slowness
  2. clean up worker multilingual UX for Vietnamese and Thai
  3. simplify withdrawal/payout identity so the product matches real operations
  4. reduce admin loading overhead that does not help longform delivery

## Task tracking update
- AIR Studio now uses task-number-based worknotes.
- The current document entry flow is:
  1. `project_status/PRODUCT_VISION.md`
  2. `project_status/NEXT_TASK.md`
  3. `project_status/WORK_INDEX.md`
  4. `worknote/AIR-xxxx.md`
- `AIR-0102` is now the longform user-flow documentation task.
- `AIR-0103` fixed the plan-route leak between longform and music.
- The next active planned task is `AIR-0104`.

## Specific findings worth preserving
- Worker language switching is expensive because:
  - the runtime persists language server-side
  - the page reloads
  - recommendation cards then trigger translation fetches again
  - translation path can fall through Gemini, Claude, and Google fallback
- Recommended topic translation is currently better treated as data to cache/store than as work to repeat on every language change.
- Wallet-address flow is a product mismatch right now:
  - local code can generate a real EVM-style wallet
  - but custody, recovery, chain handling, and operational payout flow are not productized
  - this should likely be replaced by a controlled payout identifier such as Binance ID
- Withdrawal code is internally inconsistent:
  - duplicated endpoints
  - mixed request field names
  - legacy wallet assumptions still exposed
- The admin app still eagerly loads several large datasets at startup and polls render queue every 3 seconds, which is heavier than needed while longform delivery is the priority.

## Practical caution
- `git status` currently shows many unrelated edits in the repo.
- Any future commit should be intentionally scoped.
- Template edits can appear live earlier than Python router edits if the currently running local server process has not restarted, so verification should mention which server instance was used.
- When restarting `main.py`, verify and terminate the serving multiprocessing child as well as the parent; otherwise the old child may continue to own port 8001.
