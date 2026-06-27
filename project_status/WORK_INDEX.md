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
- Status: Planned
- Commit: `N/A`
- Related files:
  - `docs/LONGFORM_USER_FLOW.md`
  - `main.py`
  - `database.py`
  - `app/routers/pages.py`
  - `app/routers/projects.py`
  - `app/routers/user_topics.py`
  - `app/routers/video.py`
- Short summary:
  Close the highest-risk contract gaps identified in the longform flow document, especially canonical project status progression and the final export/delivery path for standard workers.
- Next action:
  Decide which status transitions are authoritative for each longform step, then reduce duplicate export/upload paths into one documented worker contract.
