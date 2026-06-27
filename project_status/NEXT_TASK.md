# NEXT_TASK

## Purpose
This file is the default handoff entrypoint for Codex/ChatGPT work in AIR Studio.
Read this first before starting implementation work.

## Current Priority
1. Keep AIR Studio execution focused on `Longform Mode` completion.
2. Treat `Longform Music`, `General Shorts`, and `Shorts Commerce` as deferred modes:
   - do not actively build them unless required for shared-structure safety
   - do not let their incomplete contracts block longform delivery
3. Continue reducing noisy runtime failures from Gemini spend-cap exhaustion:
   - avoid repeated failing translation calls
   - prefer fallback paths when Gemini is unavailable

## Longform Finish Priorities
1. Remove the worker-facing language-switch latency:
   - avoid full-page-cost translation work on every language icon click
   - reduce or cache recommendation-card translation overhead
   - prefer deterministic saved translations over repeated on-demand AI translation where possible
2. Rework payout identity and withdrawal UX:
   - remove or hide wallet-address-centered UX if it is not part of the real operator flow
   - evaluate enforcing Binance ID as the payout identity instead of arbitrary external wallet addresses
   - unify duplicated withdrawal endpoints and payload shapes
3. Improve Vietnamese/Thai usability on longform worker pages:
   - normalize labels through `t()`
   - remove ad hoc language branching in core worker UI
   - clean up visible mojibake on critical pages
4. Keep plan routing project-aware:
   - make sure selected-project mode drives `/script-plan` vs `/music-plan` behavior where appropriate
5. Reduce web-admin startup load so it supports longform operations without unnecessary fetch pressure

## Immediate Next Checks
1. Profile and simplify language switching on `/projects` first.
2. Decide and document whether payout identity becomes Binance ID only.
3. Remove worker-facing wallet-address assumptions if they are not part of the real payout flow.
4. Decide whether `page_script_plan()` should keep relying on global `app_mode` or use the selected project's mode when `project_id` is present.
5. Reduce repeated Gemini failure noise in translation-heavy paths by adding cooldown / suppression.
6. Review whether duplicate recommendation cards are intentional cache behavior or whether deduplication should happen before rendering.
7. Keep a documented blocker list for deferred modes rather than pulling them into the active delivery queue.

## Working Rules
1. Before editing, check `project_status/LATEST.md` and `worknote/latest.md`.
2. Keep user-facing fixes small and runtime-verified.
3. Do not mix unrelated admin dashboard work with AIR Studio topic/project flow work unless explicitly requested.
4. Update handoff docs after meaningful work:
   - `worknote/latest.md`
   - `project_status/LATEST.md`
   - `project_status/ROADMAP.md`
   - `project_status/KNOWN_ISSUES.md` when needed

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

## Notes
- The repo has both AIR Studio runtime code and `auth-web` admin code.
- AIR Studio has four product modes, but only `Longform Mode` is an active completion target right now.
- `Longform Music`, `General Shorts`, and `Shorts Commerce` should remain structurally intact while staying outside the current active build scope.
- ChatGPT/Codex should use this file together with `PRODUCT_VISION.md` as the control surface for deciding whether a proposed task moves forward now or goes to roadmap/backlog.
- Current local branch has many unrelated in-progress changes; review diff carefully before staging.
- Port 8001 was fully restarted and browser-verified on 2026-06-27.
- Live Supabase currently returns `42703` for `categories.video_type`; music recommendation verification is data-contract blocked, not a browser failure.
