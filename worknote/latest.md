# Latest Worknote

Date: 2026-07-04
Repo: `C:\Projects\AIR-Studio`

## Why this file exists
This is the lightweight working memory for AIR Studio. It should explain what we were doing, why it mattered, and what the next session needs to know without reconstructing context from chat.

## Current understanding
- AIR Studio is a local FastAPI application with a substantial worker-facing UI under `templates/`.
- The same repo also includes a Next.js admin app under `auth-web`.
- Current main HEAD: `381fc97` — Merge pull request #25 from ibnetsoft/air-0121-image-workflow-guide

## What changed recently

### AIR-0126 — Project status document sync (2026-07-04)
- Discovered that AIR-0119, AIR-0120, AIR-0121, and PR #24 merged without project status document updates.
- Corrected `worknote/AIR-0120.md` — previous content described PR #13 documentation cleanup, which was wrong; actual AIR-0120 task was language-switch full-reload removal (`services/i18n.py`, `templates/base.html`).
- Created `worknote/AIR-0119.md` (AI provider routing centralization).
- Created `worknote/AIR-0121.md` (image workflow guide panel).
- Updated WORK_INDEX, LATEST, NEXT_TASK to reflect actual main HEAD `381fc97`.
- PR #22 (AIR-0119 finalize work index) confirmed open but diverged — recommend close.
- PRs #1–#8 confirmed superseded by AIR-0110A — recommend close.

### AIR-0121 — Image workflow guide (2026-07-03, MERGED via PR #25)
- Added image workflow guide panel to `templates/pages/image_gen.html`.
- Refined with external tool badges and ChatGPT usage hint.
- i18n keys added in `services/i18n.py`.
- Also: PR #24 (Thai i18n for settings.html) merged same day (`5c64f4d`).

### AIR-0120 — Remove worker language full reload (2026-07-02, MERGED via PR #23)
- Removed full-page reload on language icon click.
- Changed: `services/i18n.py`, `templates/base.html`.

### AIR-0119 — Centralize AI provider routing (2026-07-02, MERGED via PR #19)
- New module `services/ai_router.py` — single source of truth for provider detection and fallback.
- Changed: `services/autopilot_service.py`, `services/gemini_service.py`, `app/routers/projects.py`, `app/routers/user_topics.py`.

## Open PRs (as of 2026-07-04)
| PR | Title | Action needed |
|----|-------|---------------|
| #29 | AIR-0125 document referral migration runbook | OPEN — read-only; awaiting product owner review |
| #28 | AIR-0124 add manual referral payout processor | OPEN — read-only; awaiting product owner review |
| #27 | AIR-0123 add referral settlement pending worker | OPEN — read-only; awaiting product owner review |
| #26 | AIR-0122 implement referral default sponsor foundation | OPEN — DB migration included; awaiting CTO approval |
| #22 | AIR-0119 finalize work index | OPEN — diverged, superseded by AIR-0126; recommend close |
| #1–#8 | AIR-0102 through AIR-0109 | OPEN — all superseded by AIR-0110A (PR #9); recommend close |

## What still needs verification
1. Authenticated browser verification of the full Longform crop → upload → readiness → render-gate flow.
2. Vietnamese i18n keys for `settings.html` JS functions (follow-up from PR #24; 26 keys missing from Vietnamese section).
3. Normalize canonical longform status progression from claim through export.
4. Project-aware mode separation for remaining longform/music page family beyond `/script-plan`.

## Current longform-focused judgment
Best return for next sprint:
1. Vietnamese settings.html i18n keys (26 missing keys, small scope, clear follow-up from PR #24).
2. Normalize worker-facing longform status contract.
3. Simplify payout/withdrawal identity (separate from referral PRs #26–#29).

## Practical caution
- PR #26 contains `migration_referral_2.0.sql` — do not execute without runbook review and CTO approval.
- Per-feature AI model selection (PR #16) + AI routing centralization (AIR-0119) use `services/ai_router.py`. Do not break this architecture.
- When restarting `main.py`, terminate the serving multiprocessing child as well as the parent; otherwise the old child may continue to own port 8001.
- Gemini spend-cap failures generate noisy logs; Claude fallback is handled by `ai_router.py`.
