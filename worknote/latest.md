# Latest Worknote

Date: 2026-07-02
Repo: `C:\Projects\에어스튜디오\longformgenerator`

## Why this file exists
This is the lightweight working memory for AIR Studio. It should explain what we were doing, why it mattered, and what the next session needs to know without reconstructing context from chat.

## Current understanding
- AIR Studio is a local FastAPI application with a substantial worker-facing UI under `templates/`.
- The same repo also includes a Next.js admin app under `auth-web`.
- Current main HEAD: `cdb7c23b` — Merge pull request #17 from ibnetsoft/auth-web-lint-fixes

## What changed recently

### AIR-0117 — Project status document sync (2026-07-02)
- Confirmed PR #11 (AIR-0112) MERGED into main on 2026-07-01.
- Discovered PRs #14–#17 merged without corresponding WORK_INDEX / LATEST entries.
- Updated WORK_INDEX, LATEST, NEXT_TASK, and worknote/latest to reflect actual GitHub state.
- Cleaned NEXT_TASK of completed items (PR #11 re-review, AIR-0117 browser verification).

### PR #17 — Fix auth-web lint (MERGED 2026-07-02)
- Fixed auth-web lint execution errors and warnings.
- Lint-only; no functional changes.

### PR #16 — Per-feature AI model settings (MERGED 2026-07-02)
- Added per-feature AI model selection for all 8 generation features.
- Provider (Claude/Gemini) is auto-selected by model name.
- Existing architecture preserved — do not refactor this structure.

### PR #15 — Claude Sonnet 5 for script routing (MERGED 2026-07-02)
- Script planning and script generation now use Claude Sonnet 5.

### PR #14 — Voice admin and topic UI (MERGED 2026-07-02)
- Added admin voice management UI and bulk ElevenLabs voice registration.
- Added longform preview lock.
- Streamlined topic card translation fallback.

### PR #11 / AIR-0112 — Longform Scene asset readiness (MERGED 2026-07-01)
- Backend now owns `assets_ready`, completion percentage, missing/duplicate Scene validation, and `project_complete`.
- Render rejects incomplete projects with HTTP 409.
- Focused Longform suite: `34 passed, 1 warning`.

## Open PRs
| PR | Title | Action needed |
|----|-------|---------------|
| #13 | AIR-0118 document longform operation validation | Product owner to decide: merge or close |
| #1–#8 | Superseded by PR #9 (AIR-0110A) | Should be closed |

## What still needs verification
1. Authenticated browser verification of the full Longform crop → upload → readiness → render-gate flow (originally AIR-0113/0117 goal, still not browser-verified with dedicated test credentials).
2. Normalize canonical longform status progression from claim through export.
3. Apply project-aware mode separation to the rest of the longform/music page family.
4. Add/deploy the canonical category mode column and expose it in admin category creation/editing.

## Current longform-focused judgment
The best return now is:
1. Fix language-switch slowness (full-page reload + recommendation translation on every language icon click).
2. Clean up worker multilingual UX for Vietnamese and Thai.
3. Simplify withdrawal/payout identity so the product matches real operations.
4. Reduce admin loading overhead that does not help longform delivery.

## Practical caution
- `git status` shows only `.claude` workspace files modified — repo working tree is clean.
- Per-feature AI model selection (PR #16) uses model-name-based provider auto-selection. Do not break this architecture.
- When restarting `main.py`, verify and terminate the serving multiprocessing child as well as the parent; otherwise the old child may continue to own port 8001.
- Superseded PRs #1–#8 are still open on GitHub; they should be closed to reduce noise.
