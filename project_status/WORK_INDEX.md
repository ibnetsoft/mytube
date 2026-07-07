# WORK INDEX

## Purpose
This file is the task-number index for AIR Studio.
Future ChatGPT/Codex sessions should use this file to understand what has been done, what is active, and what should happen next without relying on long chat history.

## Read Order
1. `project_status/PRODUCT_VISION.md`
2. `project_status/NEXT_TASK.md`
3. `project_status/WORK_INDEX.md`
4. Relevant `worknote/AIR-xxxx.md`
5. `project_status/LATEST.md` and `worknote/latest.md` for extra context

## Task Rules
- Every implementation task gets a new `AIR-xxxx` ID.
- A task starts only after its Task ID is created here.
- When work finishes, update this file and the matching `worknote/AIR-xxxx.md`.
- Commit messages must include the Task ID.
- Longform-related work has priority. Non-longform work should move to roadmap/backlog unless it protects shared architecture.

## Tasks

### AIR-0099
- Status: Done
- Commit: `1b246217`
- Related files:
  - `app/routers/user_topics.py`
  - `app/routers/pages.py`
  - `templates/pages/projects.html`
  - `templates/base.html`
  - `services/i18n.py`
  - `main.py`
- Short summary:
  Hardened recommended topic claim flow, browser-validated card click -> claim-topic -> project creation -> `/script-plan` redirect, and documented why `/music-plan` verification is blocked by missing category mode schema.
- Next action:
  Preserve this as the longform topic-claim baseline while mode schema and translation performance are improved.

### AIR-0100
- Status: Done
- Commit: `4ef9c364`
- Related files:
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/PRODUCT_VISION.md`
  - `project_status/ROADMAP.md`
  - `worknote/latest.md`
- Short summary:
  Locked the longform-first product baseline, documented deferred modes, and recorded the current longform completion priorities.
- Next action:
  Introduce a task-number-based documentation system so future sessions can coordinate work by Task ID instead of long chat explanations.

### AIR-0101
- Status: Done
- Commit: `AIR-0101 commit`
- Related files:
  - `project_status/WORK_INDEX.md`
  - `worknote/TEMPLATE.md`
  - `worknote/AIR-0101.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/LATEST.md`
  - `worknote/latest.md`
- Short summary:
  Introduced the AIR task tracking document system so future ChatGPT/Codex sessions can resume from Git-tracked Task IDs, worknotes, and control documents.
- Next action:
  Start the next active implementation task as `AIR-0102` and use the new task-tracking workflow from the beginning.

### AIR-0102
- Status: Done
- Commit: `32d4f6aa`
- Related files:
  - `docs/LONGFORM_USER_FLOW.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/ROADMAP.md`
  - `worknote/latest.md`
  - `worknote/AIR-0102.md`
- Short summary:
  Documented the current `Longform Mode` worker flow from login to export using real routes, BFF handlers, local/Supabase data ownership, stage states, and unresolved contract gaps.
- Next action:
  Use the new longform flow document as the basis for `AIR-0103`, starting with status ownership and export-path normalization for the worker journey.

### AIR-0103
- Status: Done
- Commit: `54f00e15`
- Related files:
  - `app/routers/pages.py`
  - `app/routers/user_topics.py`
  - `templates/pages/projects.html`
  - `templates/base.html`
  - `docs/LONGFORM_USER_FLOW.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `worknote/latest.md`
  - `worknote/AIR-0103.md`
- Short summary:
  Made plan routing project-aware so longform topic claims stay on `/script-plan`, restricted `/music-plan` to real `longform_music` projects, and blocked standard memberships from entering the music workflow.
- Next action:
  Continue the same project-aware separation across the remaining longform/music routes and tighten the standard-worker publish/export contract.

### AIR-0104
- Status: Planned
- Commit: `N/A`
- Related files:
  - `app/routers/pages.py`
  - `templates/base.html`
  - `docs/LONGFORM_USER_FLOW.md`
  - `main.py`
  - `app/routers/video.py`
  - `project_status/NEXT_TASK.md`
- Short summary:
  Extend the project-aware longform/music separation beyond the plan page and finalize the worker-safe export/publish contract for standard longform members.
- Next action:
  Audit the rest of the page family (`image-gen`, `audio-gen`, `render`, `title-desc`, upload/export`) and remove remaining global-mode shortcuts that can misroute longform workers.

### AIR-0106
- Status: Done
- Commit: `bdf63742`
- Related files:
  - `docs/LONGFORM_PRODUCTION_PIPELINE.md`
  - `docs/LONGFORM_USER_FLOW.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `worknote/AIR-0106.md`
  - `worknote/latest.md`
- Short summary:
  Audited the real Longform production pipeline and fixed the documented product boundary: AIR Studio creates scripts, scenes, and prompts, while users generate, upscale, and animate assets through external AI services and import the results.
- Next action:
  AIR-0107 should make bulk scene assignment deterministic and safe by adding filename parsing, range and duplicate validation, missing-scene reporting, and non-destructive import review.

### AIR-0107
- Status: Done
- Commit: `9054841e`
- Related files:
  - `app/routers/image.py`
  - `services/scene_asset_matcher.py`
  - `templates/pages/image_gen.html`
  - `tests/test_scene_asset_matcher.py`
  - `docs/UPLOAD_PIPELINE.md`
  - `docs/LONGFORM_PRODUCTION_PIPELINE.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/ROADMAP.md`
  - `worknote/AIR-0107.md`
  - `worknote/latest.md`
- Short summary:
  Validated the Longform media import flow and added filename-first scene matching, AI fallback, range and duplicate protection, missing-scene reporting, and an upload result summary.
- Next action:
  AIR-0108 should connect 2x2 crop output directly to project scene slots while reusing the AIR-0107 import safety contract.

### AIR-0108
- Status: Done
- Commit: `d8310f89`
- Related files:
  - `templates/pages/image_gen.html`
  - `tests/test_scene_asset_review_ui.py`
  - `docs/SCENE_ASSET_REVIEW.md`
  - `docs/UPLOAD_PIPELINE.md`
  - `docs/LONGFORM_PRODUCTION_PIPELINE.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/ROADMAP.md`
  - `worknote/AIR-0108.md`
  - `worknote/latest.md`
- Short summary:
  Added a persisted-data Scene Asset Review panel, final clip ordering, missing-scene readiness gate, and safe independent image/video replacement for Longform projects.
- Next action:
  AIR-0109 should connect 2x2 crop output to project scenes, add unmatched-asset reassignment, and define a canonical backend `assets_ready` policy.

### AIR-0109
- Status: Done
- Commit: `3763fd89`
- Related files:
  - `templates/pages/image_crop.html`
  - `templates/pages/image_gen.html`
  - `tests/test_scene_crop_import_ui.py`
  - `tests/test_scene_asset_matcher.py`
  - `docs/SCENE_ASSET_PIPELINE.md`
  - `docs/LONGFORM_PRODUCTION_PIPELINE.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/ROADMAP.md`
  - `worknote/AIR-0109.md`
  - `worknote/latest.md`
- Short summary:
  Connected 2x2 crop panels to explicit project Scene slots with deterministic filenames, direct empty-slot import, and documented image/video matching and large-batch behavior.
- Next action:
  AIR-0110 should browser-verify the real crop/import/review flow and implement a canonical backend `assets_ready` policy.

### AIR-0110A
- Status: Done
- Commit: `6169b686`
- Related files:
  - Longform runtime and UI files consolidated from AIR-0106 through AIR-0109
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `worknote/AIR-0110A.md`
  - `worknote/latest.md`
- Short summary:
  Rebuilt AIR-0106 through AIR-0109 as one clean integration branch from current `origin/main`, excluding the unrelated `36ac3364 feat(air-0001)` Shorts, payout, and database changes.
- Next action:
  Merge the AIR-0110A clean integration PR instead of PR #5, #6, #7, or #8, then continue AIR-0110 browser verification.

### AIR-0111
- Status: Done
- Commit: `716bcb09`
- Related files:
  - `docs/LONGFORM_MVP_VALIDATION.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/ROADMAP.md`
  - `worknote/AIR-0111.md`
  - `worknote/latest.md`
- Short summary:
  Validated the 17-stage Longform production journey against runtime code,
  focused tests, the login screen, and actual SQLite state. The product is not
  Beta-ready because Scene readiness and project completion do not share a
  canonical backend contract.
- Next action:
  AIR-0112 should persist and enforce canonical `assets_ready` and
  `project_complete` rules across review, render/export, and project status UI.

### AIR-0112
- Status: Done
- Commit: `9b4725e1`
- Related files:
  - `services/longform_asset_readiness.py`
  - `database.py`
  - `app/routers/image.py`
  - `app/routers/video.py`
  - `main.py`
  - `templates/pages/image_gen.html`
  - `tests/test_longform_asset_readiness.py`
  - `tests/test_scene_asset_review_ui.py`
  - `docs/LONGFORM_MVP_VALIDATION.md`
  - `docs/LONGFORM_USER_FLOW.md`
  - `docs/LONGFORM_PRODUCTION_PIPELINE.md`
  - `docs/SCENE_ASSET_PIPELINE.md`
  - `worknote/AIR-0112.md`
- Short summary:
  Added a backend-owned Longform `image_or_video` Scene readiness contract,
  persisted completion state, exposed it through project and upload APIs, and
  blocked render when Scene assets are incomplete.
- Next action:
  AIR-0113 should browser-verify the complete authenticated crop, upload,
  matching, refresh, readiness, and render-gating flow using a safe test worker.

### AIR-0115
- Status: Done
- Commit: `4007870c`
- Related files:
  - `worknote/AIR-0115.md`
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `worknote/latest.md`
- Short summary:
  Corrected local `origin` from `ibnetsoft/ilddang` to `ibnetsoft/mytube`, confirmed GitHub CLI authentication, verified PR #11 exists and is OPEN at `air-0112-longform-e2e-fix-pass`, confirmed commit `f983dcf7`, and created this cleanup branch from mytube `origin/main` without carrying unrelated feature changes.
- Next action:
  AIR-0116 should update PR #11 against the merged AIR-0115 main state and resolve only documentation/status conflicts.

### AIR-0116
- Status: Done
- Commit: `489be548`
- PR: #11 (MERGED 2026-07-01)
- Related files:
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/WORK_INDEX.md`
  - `worknote/latest.md`
  - `worknote/AIR-0116.md`
- Short summary:
  Resolved PR #11 conflicts from AIR-0115 / PR #12 by preserving AIR-0112 Longform readiness records, preserving AIR-0115 mytube remote cleanup records, and limiting changes to documentation/status files. PR #11 merged into main on 2026-07-01.
- Next action:
  AIR-0117 syncs project status documents after PR #11–#17 merged.

### AIR-0117
- Status: Done
- Commit: `(this PR)`
- PR: air-0117-project-status-sync
- Related files:
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `project_status/WORK_INDEX.md`
  - `worknote/latest.md`
  - `worknote/AIR-0117.md`
- Short summary:
  Confirmed PR #11 merged. Discovered PRs #14–#17 (voice admin, Sonnet 5, per-feature AI models, auth-web lint) had merged without corresponding WORK_INDEX entries. Synchronized all project status documents with the actual GitHub state. Main HEAD is now `cdb7c23b`.
- Next action:
  Product owner to decide next Sprint. Recommended candidates: language-switch latency, Vietnamese/Thai UX, payout identity simplification.

### AIR-0118
- Status: Done
- Commit: `c7ce03d3`
- PR: #20 (MERGED 2026-07-02)
- Related files:
  - `docs/LONGFORM_OPERATION_VALIDATION.md`
  - `worknote/AIR-0118.md`
  - `worknote/AIR-0120.md`
- Short summary:
  Validated the Longform operator workflow. Browser execution was blocked due to unavailability of safe test credentials. Documented current gate status, focused test evidence, and admin publish/export blockers. Preserved validation docs via PR #20 after PR #13 was closed due to merge conflicts with main.
- Next action:
  Re-run the complete Longform operator workflow with dedicated credentials and real external assets to complete authenticated browser-level validation.

### AIR-0119
- Status: Done
- Commit: `24d06f9`
- PR: #19 (MERGED 2026-07-02)
- Related files:
  - `services/ai_router.py` (new)
  - `services/autopilot_service.py`
  - `services/gemini_service.py`
  - `app/routers/projects.py`
  - `app/routers/user_topics.py`
- Short summary:
  Centralized scattered Claude/Gemini provider selection logic into a single `services/ai_router.py` module. All AI generation calls now share one source of truth for provider detection (`detect_provider`) and fallback routing (`generate_text`). No functional behavior changes; fallback to Gemini on Claude failure preserved.
- Next action:
  AIR-0120 removes the worker-facing full-page reload on language switch.

### AIR-0120
- Status: Done
- Commit: `2046b53`
- PR: #23 (MERGED 2026-07-02)
- Related files:
  - `services/i18n.py`
  - `templates/base.html`
- Short summary:
  Removed the full-page reload triggered by worker-facing language switching. Language icon clicks previously caused a complete page reload plus on-demand recommendation translation through the Gemini → Claude → Google fallback chain. Base template and i18n service updated to eliminate this reload.
- Next action:
  AIR-0121 adds an image workflow guide panel to `image_gen.html`.

### AIR-0121
- Status: Done
- Commit: `381fc97`
- PR: #25 (MERGED 2026-07-03)
- Related files:
  - `templates/pages/image_gen.html`
  - `services/i18n.py`
  - `templates/pages/settings.html`
- Short summary:
  Added an image workflow guide panel to `image_gen.html` to help workers understand the external AI image generation pipeline. Refined with external tool badges and a ChatGPT usage hint. i18n keys added for badge labels and hint text.
- Next action:
  AIR-0126 synchronizes all project status documents (WORK_INDEX, LATEST, NEXT_TASK, worknote/latest) to reflect actual GitHub main state after AIR-0119 through AIR-0121 merged without document updates.

### AIR-0126
- Status: Done
- Commit: `939a301`
- PR: #30 (OPEN — awaiting product owner merge)
- Branch: `air-0126-project-status-sync`
- Related files:
  - `project_status/WORK_INDEX.md`
  - `project_status/LATEST.md`
  - `project_status/NEXT_TASK.md`
  - `worknote/latest.md`
  - `worknote/AIR-0119.md` (created)
  - `worknote/AIR-0120.md` (corrected)
  - `worknote/AIR-0121.md` (created)
- Short summary:
  Synchronized all project status documents with actual GitHub main state after AIR-0119, AIR-0120, AIR-0121, and PR #24 merged without document updates. Corrected worknote/AIR-0120.md (previously described PR #13 documentation cleanup instead of language full-reload removal). Created missing worknotes for AIR-0119 and AIR-0121.
- Next action:
  AIR-0127 closes superseded PRs #1–#8 and #22 after PR #30 merges.

### AIR-0127
- Status: Blocked — waiting for PR #30 (AIR-0126) to merge before closing superseded PRs
- Branch: none yet
- Scope: Close PRs #1–#8 and #22 with superseded comments after PR #30 is merged
- Next action:
  After PR #30 merges, run: gh pr close 1 2 3 4 5 6 7 8 22 with appropriate comments.

### AIR-0128
- Status: Done (PR open)
- Commit: `62c432c`
- PR: #31 (OPEN — awaiting product owner review and migration approval)
- Branch: `air-0128-db-persistent-translation`
- Related files:
  - `app/routers/user_topics.py`
  - `auth-web/app/api/admin/topics-queue/route.ts`
  - `migrations/air_0128_topics_queue_translation_columns.sql` (new)
  - `scripts/backfill_topic_translations.py` (new)
  - `tests/test_topic_translation_db.py` (new)
- Short summary:
  Replaced runtime AI translation for recommended topic cards with DB-persistent translation. Added `_fetch_stored_translations()` and `_save_translations_to_db()` to `user_topics.py`. The `/api/user/recommended-topics/translations` endpoint now reads from Supabase `topics_queue` translation columns first and falls back to AI only for NULL rows, saving new translations back to DB. auth-web PUT handler resets translation columns on topic text edit. Migration SQL adds 6 nullable TEXT columns. Backfill script provided for existing rows.
- Next action:
  1. Product owner approves and merges PR #31.
  2. Apply `migrations/air_0128_topics_queue_translation_columns.sql` to Supabase.
  3. Run backfill: `python scripts/backfill_topic_translations.py --lang vi` (then en, th).

### AIR-0129
- Status: Done (PR open)
- Commit: `(this PR)`
- PR: air-0129-admin-auto-translation (OPEN)
- Branch: `air-0129-admin-auto-translation`
- Related files:
  - `auth-web/app/api/admin/topics-queue/route.ts`
  - `migrations/air_0129_topics_queue_translation_status.sql` (new)
  - `tests/test_topic_translation_admin_pipeline.py` (new)
- Short summary:
  Added admin auto-translation pipeline to route.ts. POST (topic generation) and PUT (topic edit) handlers now fire a void background Gemini task immediately after returning 200 OK. The background task translates topic+category_name into vi, en, th via three sequential Gemini calls, saves all 6 columns plus `translated_at` and `translation_status=completed` to Supabase. On failure only `translation_status=failed` is written; the admin save is never blocked. Migration adds `translated_at TIMESTAMPTZ` and `translation_status TEXT` with CHECK constraint. User App (user_topics.py) behavior unchanged — it still reads the 6 translation columns and ignores the new admin-only columns. 10 new tests pass (24 total with AIR-0128 suite).
- Next action:
  1. Product owner approves and merges PR #31 (AIR-0128) first.
  2. Apply both migration SQLs to Supabase (AIR-0128 first, then AIR-0129).
  3. Merge this PR.
  4. Run backfill: `python scripts/backfill_topic_translations.py --lang vi` (then en, th).

## Non-AIR Merged PRs (outside AIR task numbering)

### PR #24 — Add Thai i18n keys for settings.html (Upload QA, Withdrawal, Referral)
- Status: Merged 2026-07-03
- Branch: `thai-ux-i18n-fix`
- Commit: `5c64f4d`
- Short summary: Added 28 Thai translation keys (net +15 new keys, +13 restored keys) to `services/i18n.py`. Replaced hardcoded Korean strings in `templates/pages/settings.html` Upload QA Settings section with Thai Jinja2 conditionals. All 26 JS runtime `i18n.*` references in settings.html confirmed present in Thai section. Vietnamese section equivalent keys noted as a follow-up item.

### PR #14 — feat: topic UI and admin ElevenLabs voice management
- Status: Merged 2026-07-02
- Branch: `codex/voice-admin-production`
- Commit: `dfbf629c`
- Short summary: Added admin voice management UI, bulk ElevenLabs voice registration, longform preview lock, and streamlined topic card translation fallback.

### PR #15 — Enable Claude Sonnet 5 for script planning and generation
- Status: Merged 2026-07-02
- Branch: `claude-sonnet-5-script-routing`
- Commit: `974f4c7a`
- Short summary: Enabled Claude Sonnet 5 model for script planning and script generation routes.

### PR #16 — Add per-feature AI model settings
- Status: Merged 2026-07-02
- Branch: `feature/per-feature-ai-models`
- Commit: `1ba1309a`
- Short summary: Added per-feature AI model selection (Topic, Title, Script Planning, Script Generation, Image Prompt, Translation, Image Generation, Video Generation).

### PR #17 — Fix auth-web lint execution and warnings
- Status: Merged 2026-07-02
- Branch: `auth-web-lint-fixes`
- Commit: `cdb7c23b`
- Short summary: Fixed auth-web lint execution errors and resolved lint warnings. Lint-only change, no functional modifications.

- [AIR-0209](../worknote/AIR-0209.md) - Planning Scene Contract Refactor (DONE)
- [AIR-0212](../worknote/AIR-0212.md) - Master Documentation Overhaul (DONE)
- [AIR-0213](../worknote/AIR-0213.md) - Scene Pipeline E2E Tests + Unmatched Asset Board (DONE)
- [AIR-0214](../worknote/AIR-0214.md) - Windows Installer + Auto-Update System (DONE — PR #67)
- [AIR-0215](../worknote/AIR-0215.md) - Windows Updater Hardening (DONE — PR #67)
- [AIR-0216](../worknote/AIR-0216.md) - Release Pipeline Automation (DONE)
- [AIR-0217](../worknote/AIR-0217.md) - Real-Install E2E QA (PLANNED — manual)
- [AIR-0218](../worknote/AIR-0218.md) - GitHub Actions Release Automation (DONE)