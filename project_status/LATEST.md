# LATEST

## Project
AIR Studio / LongformGenerator

## Snapshot
- Desktop/local-first FastAPI application for AI-assisted video production.
- Includes a paired Next.js admin app under `auth-web`.
- AIR Studio currently carries four product modes: `longform`, `longform_music`, `general_shorts`, and `shorts_commerce`.
- The codebase is already partly reorganized in a BFF style, and current execution priority is to finish `Longform Mode` without breaking the structural boundaries of the other modes.

## Product Focus
1. `Longform Mode`
   Current highest-priority development target and the main online worker platform for longform video production.
2. `Longform Music`
   Internal-use mode only for now. Keep the structure intact, but defer active development.
3. `General Shorts`
   Intended later as a shorts/reels/tiktok-linked marketing platform. Currently internal-use oriented and not an active build target.
4. `Shorts Commerce`
   Internal-use mode only for now. Keep the structure intact, but defer active development.

## Current Active Themes
1. Complete `Longform Mode` end-to-end worker flow first.
2. Stabilize personalized recommended topics on the project page.
3. Keep runtime sync between local app and web admin policy/settings reliable.
4. Preserve mode boundaries so deferred modes do not get structurally damaged while longform work continues.

## Longform Completion Assessment
- The highest-impact blocker for `Longform Mode` completion is runtime slowness around language switching and recommendation-card translation.
- Worker-facing multilingual UX for Vietnamese and Thai users is still incomplete:
  - some labels remain English-only
  - some strings are still rendered through ad hoc per-language conditionals
  - some legacy mojibake text remains in templates
- Withdrawal and wallet behavior is not aligned with the intended product policy:
  - the runtime still exposes wallet-address-based withdrawal concepts
  - the backend mixes multiple withdrawal endpoints and field names
  - the current local wallet generation model is not a strong fit for production payout operations
- The admin app still loads too much data eagerly on startup and polls render queue data aggressively, which adds avoidable overhead while `Longform Mode` is the primary delivery target.

## Recommended Priority Order
1. Remove the language-switch bottleneck in worker-facing longform screens.
2. Simplify payout/withdrawal policy around operator-controlled payout identity instead of external wallet-address UX.
3. Clean up Vietnamese/Thai worker UX on core longform pages.
4. Stabilize project-mode-aware routing so the selected project, not only global mode, drives plan-page behavior.
5. Reduce web-admin eager loading and polling pressure.

## Recent Relevant Changes
- `AIR-0101`
  Introduced the task-number-based document system with `WORK_INDEX.md`, per-task worknotes, and task-ID-driven operating rules.
- `AIR-0100`
  Locked the longform-first product baseline and documented deferred modes plus longform completion priorities.
- `AIR-0099`
  Stabilized recommended topic claim flow and browser-validated longform recommendation card redirect behavior.
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
- Completed a code-based review of what most directly improves `Longform Mode` completion:
  - language switching currently triggers full-page reload plus recommendation translation work
  - recommendation translation currently retries through Gemini, Claude, then Google fallback
  - wallet/withdrawal code still reflects wallet-address-centered assumptions
  - withdrawal endpoints and payload fields are duplicated/inconsistent
  - admin dashboard still performs heavy eager data loading at startup

## Current Risks
- Gemini spend-cap failures generate noisy runtime logs and can slow fallback flows.
- The repo contains concurrent unrelated local changes; commit scope must be explicit.
- `longform` card routing to `/script-plan` is verified on the primary 8001 runtime.
- `/music-plan` cannot be verified until the admin/Supabase category schema exposes a mode field (currently expected as `categories.video_type`) and at least one pending music topic exists.
- The existence of four product modes can pull implementation toward mixed concerns; current work should stay centered on `Longform Mode` unless a change is required to preserve shared structure.
- Worker-facing language switching is still more expensive than it should be because UI language persistence, full reload, and dynamic topic translation are tightly coupled.
- Wallet-address-based payout UX is still exposed despite the product leaning toward operator-controlled payout identity such as Binance ID.
- `main.py` uses multiprocessing; a restart must terminate both the parent and its serving child or the old child can keep port 8001 alive.
- Some legacy files contain mojibake comments/text, which makes targeted editing slightly harder.

## Source of Truth
- Runtime/API behavior: Python app in root repo
- Admin policy/state: `auth-web` and Supabase-backed settings
- Local project persistence: SQLite via `database.py`
