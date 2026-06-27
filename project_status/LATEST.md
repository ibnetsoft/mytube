# LATEST

## Project
AIR Studio / LongformGenerator

## Snapshot
- Desktop/local-first FastAPI application for AI-assisted video production.
- Includes a paired Next.js admin app under `auth-web`.
- Supports longform, music-oriented longform, shorts, publishing, translation, TTS, rendering, and topic assignment flows.

## Current Active Themes
1. Personalized recommended topics on the project page.
2. Runtime sync between local app and web admin policy/settings.
3. Multilingual UI and translated display content for worker-facing screens.
4. Payout and duration lock propagation from admin policy into created projects.

## Recent Relevant Changes
- Added personalized topic recommendation flow and card UI.
- Added translated subtitle/category display for recommended topic cards.
- Split `/projects` into topic view and project list view.
- Added payout and duration metadata to recommended topic cards.
- Added fallback translation path when Gemini translation is unavailable.
- Fixed recommendation claim flow so recommendation UUIDs can resolve to the underlying `topics_queue` record.
- Fixed backward-compatibility in `claim-topic` resolution so stale/open browser tabs that still submit cached recommendation IDs resolve through `user_topic_recommendations` before treating the value as a raw `topics_queue.id`.
- Removed the blocking native `confirm()` step from recommended topic cards and replaced it with in-flight click guarding on the card itself.
- Verified with `TestClient` that:
  - `GET /api/user/recommended-topics` returns claimable `topics_queue.id` values
  - `POST /api/user/claim-topic` now succeeds
  - created project settings keep `script_style`, `image_style`, `style_locked`, `duration_locked`, `assigned_duration_minutes`, `estimated_payout`, and `target_language`
- Fixed the claim flow success condition to accept Supabase `PATCH 204 No Content`.
- Verified in a fresh browser session against a fresh runtime server on `http://127.0.0.1:8011` that:
  - recommended topic card click succeeds
  - project is created (`project_id=254` during verification)
  - redirect lands on `/script-plan?project_id=254&auto=true&topic=...`
  - the script-plan page visibly loads and populates the topic title
- Fully restarted the primary `http://127.0.0.1:8001` runtime, including its orphaned multiprocessing child that had continued serving the old router code.
- Re-verified the recommendation flow in the logged-in Chrome session against port 8001:
  - clicked the unique economy recommendation card
  - claim-topic succeeded
  - project `256` was created from topic queue record `1937`
  - redirect landed on `/script-plan?project_id=256&auto=true&topic=...`
  - the plan page loaded the selected topic and locked admin metadata
  - SQLite persisted `app_mode=longform`, duration `15`, payout `4.0`, script style `news`, and image style `cinematic`
- Checked the live Supabase schema for music-mode verification:
  - `categories.video_type` does not exist in the deployed database
  - querying that column returns PostgreSQL error `42703`
  - the claim route therefore falls back every category to `longform`
  - no real `longform_music` recommendation can currently be produced or browser-verified

## Current Risks
- Gemini spend-cap failures generate noisy runtime logs and can slow fallback flows.
- The repo contains concurrent unrelated local changes; commit scope must be explicit.
- `longform` card routing to `/script-plan` is verified on the primary 8001 runtime.
- `/music-plan` cannot be verified until the admin/Supabase category schema exposes a mode field (currently expected as `categories.video_type`) and at least one pending music topic exists.
- `main.py` uses multiprocessing; a restart must terminate both the parent and its serving child or the old child can keep port 8001 alive.
- Some legacy files contain mojibake comments/text, which makes targeted editing slightly harder.

## Source of Truth
- Runtime/API behavior: Python app in root repo
- Admin policy/state: `auth-web` and Supabase-backed settings
- Local project persistence: SQLite via `database.py`
