# NEXT_TASK

## Purpose
This file is the default handoff entrypoint for Codex/ChatGPT work in AIR Studio.
Read this first before starting implementation work.

## Task Pointer
Next: `AIR-0119` — rerun the full Longform operator workflow with dedicated worker/admin test credentials and real external assets, then validate admin publish/export readiness end to end.

## Integration Note
- AIR-0110A clean integration was merged through PR #9 at `f5905d07`.
- PR #5, #6, #7, and #8 remain superseded and must not be merged.
- AIR-0111 determined that Longform is not ready for external Beta.
- AIR-0115 corrected local `origin` to `https://github.com/ibnetsoft/mytube.git` and confirmed PR #11 exists in `ibnetsoft/mytube`.

## AIR-0119 Goal
Re-run the complete Longform operator workflow with dedicated credentials and real external assets after AIR-0118 documented the current authenticated-browser blocker:

1. Provision or identify a safe Longform test worker and deterministic project.
2. Import a real 2x2 grid into empty Scene slots.
3. Upload numbered images and videos and verify automatic matching.
4. Confirm missing, duplicate, invalid, and occupied files are visible.
5. Refresh and verify Scene order and canonical readiness restoration.
6. Confirm incomplete projects cannot render.
7. Confirm a complete project can pass the readiness gate.
8. Validate whether admin publish/export needs an additional readiness gate.

## Current Priority
1. Keep AIR Studio execution focused on `Longform Mode` completion.
2. Treat `Longform Music`, `General Shorts`, and `Shorts Commerce` as deferred modes:
   - do not actively build them unless required for shared-structure safety
   - do not let their incomplete contracts block longform delivery
3. Continue reducing noisy runtime failures from Gemini spend-cap exhaustion:
   - avoid repeated failing translation calls
   - prefer fallback paths when Gemini is unavailable

## Longform Finish Priorities
1. Normalize the longform worker state contract:
   - define canonical project-status ownership from claim through export
   - reduce UI-only stage inference where backend-owned status is required
   - align final render/export success conditions across worker-facing pages
2. Finish project-aware longform/music route separation:
   - remove remaining global-mode shortcuts from worker page routing
   - make selected-project mode authoritative where a `project_id` exists
   - keep standard longform workers out of the internal music workflow
3. Rework payout identity and withdrawal UX:
   - remove or hide wallet-address-centered UX if it is not part of the real operator flow
   - evaluate enforcing Binance ID as the payout identity instead of arbitrary external wallet addresses
   - unify duplicated withdrawal endpoints and payload shapes
4. Remove the worker-facing language-switch latency:
   - avoid full-page-cost translation work on every language icon click
   - reduce or cache recommendation-card translation overhead
   - prefer deterministic saved translations over repeated on-demand AI translation where possible
5. Improve Vietnamese/Thai usability on longform worker pages:
   - normalize labels through `t()`
   - remove ad hoc language branching in core worker UI
   - clean up visible mojibake on critical pages
6. Reduce web-admin startup load so it supports longform operations without unnecessary fetch pressure

## Immediate Next Checks
1. Use dedicated test credentials; do not reuse or expose a real password.
2. Browser-check project 195 shows 18% and Scene 3-11 missing.
3. Browser-check project 188 shows 100% under `image_or_video`.
4. Exercise one safe upload/replacement and refresh.
5. Record browser evidence for the readiness badge and progress.

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
   - `project_status/ROADMAP.md`
   - `project_status/KNOWN_ISSUES.md` when needed
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
- ChatGPT/Codex should use this file together with `PRODUCT_VISION.md` and `WORK_INDEX.md` as the control surface for deciding whether a proposed task moves forward now or goes to roadmap/backlog.
- `AIR-0102` documented the current longform flow.
- `AIR-0103` fixed the highest-risk plan-route leak by keeping longform claims on `/script-plan` and restricting `/music-plan` to internal music use.
- Current local branch has many unrelated in-progress changes; review diff carefully before staging.
- Port 8001 was fully restarted and browser-verified on 2026-06-27.
- Live Supabase currently returns `42703` for `categories.video_type`; music recommendation verification is data-contract blocked, not a browser failure.
