# NEXT_TASK

## Purpose
This file is the default handoff entrypoint for Codex/ChatGPT work in AIR Studio.
Read this first before starting implementation work.

## Task Pointer
Next: `AIR-0104`

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
1. Extend the project-aware routing fix from `/script-plan` and `/music-plan` into the rest of the longform/music page family.
2. Decide whether standard workers should only use `admin-publish-request` as the final export path.
3. Use `docs/LONGFORM_USER_FLOW.md` to define one canonical longform status progression from claim -> plan -> script -> TTS -> render -> export.
4. Decide and document whether payout identity becomes Binance ID only.
5. Remove worker-facing wallet-address assumptions if they are not part of the real payout flow.
6. Profile and simplify language switching on `/projects`.
7. Reduce repeated Gemini failure noise in translation-heavy paths by adding cooldown / suppression.

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
