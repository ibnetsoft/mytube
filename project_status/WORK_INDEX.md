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
- Commit: `pending`
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
