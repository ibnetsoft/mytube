# NEXT_TASK

## Purpose
This file is the default handoff entrypoint for Codex/ChatGPT work in AIR Studio.
Read this first before starting implementation work.

## Current State (as of 2026-07-02)

### Main HEAD
`cdb7c23b` — Merge pull request #17 from ibnetsoft/auth-web-lint-fixes

### Recently Merged PRs
| PR | Title | Merged |
|----|-------|--------|
| #17 | Fix auth-web lint execution and warnings | 2026-07-02 |
| #16 | Add per-feature AI model settings | 2026-07-02 |
| #15 | Enable Claude Sonnet 5 for script planning and generation | 2026-07-02 |
| #14 | feat: topic UI and admin ElevenLabs voice management | 2026-07-02 |
| #12 | AIR-0115 document mytube remote cleanup | 2026-07-01 |
| #11 | AIR-0112 enforce Longform Scene asset readiness | 2026-07-01 |
| #10 | AIR-0111 Longform MVP end-to-end validation | 2026-07-01 |
| #9  | AIR-0110A clean Longform integration | 2026-07-01 |

### Open PRs
| PR | Title | Action |
|----|-------|--------|
| #13 | AIR-0118 document longform operation validation | Awaiting review / merge decision |
| #1–#8 | Superseded by AIR-0110A / PR #9 | Should be closed |

## Task Pointer
Next task ID: `AIR-0119` (to be assigned by product owner after Sprint decision)

## Current Priority
1. Keep AIR Studio execution focused on `Longform Mode` completion.
2. Treat `Longform Music`, `General Shorts`, and `Shorts Commerce` as deferred modes.
3. Continue reducing noisy runtime failures from Gemini spend-cap exhaustion.

## Longform Finish Priorities
1. Remove the language-switch bottleneck in worker-facing longform screens.
   - Worker language switching triggers full-page reload + recommendation translation
   - Translation path falls through Gemini → Claude → Google fallback
   - Prefer cached/stored translations over repeated on-demand AI translation
2. Clean up Vietnamese/Thai worker UX on core longform pages.
   - Normalize labels through `t()`
   - Remove ad hoc language branching in core worker UI
   - Clean up visible mojibake on critical pages
3. Simplify payout/withdrawal identity.
   - Remove or hide wallet-address-centered UX
   - Evaluate enforcing Binance ID as payout identity instead of arbitrary wallet addresses
   - Unify duplicated withdrawal endpoints and payload shapes
4. Normalize the longform worker state contract.
   - Define canonical project-status ownership from claim through export
   - Reduce UI-only stage inference where backend-owned status is required
5. Reduce web-admin startup load.
   - Admin app loads too much data eagerly on startup
   - Polls render queue every 3 seconds — heavier than needed for longform delivery focus
6. Finish project-aware longform/music route separation.
   - Some longform/music pages still branch from global mode rather than selected-project mode
   - `/script-plan` is fixed; audit and fix the rest of the page family

## Open Questions for Product Owner
1. Should PR #13 (AIR-0118) be merged or closed?
2. Should superseded PRs #1–#8 be closed?
3. Which Longform Finish Priority above is the next Sprint target?

## Working Rules
1. Before editing, check `project_status/PRODUCT_VISION.md`, `project_status/NEXT_TASK.md`, and `project_status/WORK_INDEX.md`.
2. Every new implementation task must get a new `AIR-xxxx` Task ID before work starts.
3. Keep user-facing fixes small and runtime-verified.
4. Do not mix unrelated admin dashboard work with AIR Studio topic/project flow work unless explicitly requested.
5. After meaningful work, update:
   - matching `worknote/AIR-xxxx.md`
   - `project_status/WORK_INDEX.md`
   - `worknote/latest.md`
   - `project_status/LATEST.md`
   - `project_status/NEXT_TASK.md`
6. Commit messages must include the Task ID.

## Key Files
- `main.py`
- `database.py`
- `app/routers/pages.py`
- `app/routers/projects.py`
- `app/routers/user_topics.py`
- `templates/pages/projects.html`
- `templates/base.html`
- `services/gemini_service.py`
- `services/claude_service.py`
- `services/web_admin_client.py`
- `auth-web/components/DashboardContent.tsx`
- `docs/LONGFORM_USER_FLOW.md`

## Notes
- The repo has both AIR Studio runtime code and `auth-web` admin code.
- AIR Studio has four product modes, but only `Longform Mode` is an active completion target right now.
- `Longform Music`, `General Shorts`, and `Shorts Commerce` should remain structurally intact while staying outside the current active build scope.
- Per-feature AI model selection is now live (PR #16). Provider is auto-selected by model name. Do not break this structure.
- ElevenLabs voice management and longform preview lock are now live (PR #14).
- `main.py` uses multiprocessing; a restart must terminate both the parent and its serving child or the old child can keep port 8001 alive.
