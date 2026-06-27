# NEXT_TASK

## Purpose
This file is the default handoff entrypoint for Codex/ChatGPT work in AIR Studio.
Read this first before starting implementation work.

## Current Priority
1. Add and deploy the category-mode data contract required for music recommendations:
   - add `categories.video_type` (or agree on an equivalent canonical field)
   - allow values `longform` and `longform_music`
   - create at least one pending topic under a `longform_music` category
2. Then verify the music-mode branch end to end:
   - a `longform_music` recommendation card
   - claim-topic success
   - project creation
   - redirect to `/music-plan`
3. Reduce noisy runtime failures from Gemini spend-cap exhaustion:
   - avoid repeated failing translation calls
   - prefer fallback paths when Gemini is unavailable

## Immediate Next Checks
1. Prepare and apply the Supabase migration for the category mode field used by `claim-topic`.
2. Confirm project routing respects:
   - `longform` -> `/script-plan` (done on primary 8001 runtime, project `256`)
   - `longform_music` -> `/music-plan` (blocked by missing deployed category mode column)
3. Reduce repeated Gemini failure noise in translation-heavy paths by adding cooldown / suppression.
4. Decide whether `page_script_plan()` should keep relying on global `app_mode` or use the selected project's mode when `project_id` is present.
5. Review whether duplicate recommendation cards are intentional cache behavior or whether deduplication should happen before rendering.

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
- Current local branch has many unrelated in-progress changes; review diff carefully before staging.
- Port 8001 was fully restarted and browser-verified on 2026-06-27.
- Live Supabase currently returns `42703` for `categories.video_type`; music recommendation verification is data-contract blocked, not a browser failure.
