# NEXT_TASK

## Purpose
This file is the default handoff entrypoint for Codex/ChatGPT work in AIR Studio.
Read this first before starting implementation work.

## Current State (as of 2026-07-04)

### Main HEAD
`381fc97` — Merge pull request #25 from ibnetsoft/air-0121-image-workflow-guide

### Recently Merged PRs
| PR | Title | Merged |
|----|-------|--------|
| #25 | AIR-0121 refine image workflow guide final UI | 2026-07-03 |
| #24 | Add Thai i18n keys for settings.html (Upload QA, Withdrawal, Referral) | 2026-07-03 |
| #23 | AIR-0120 remove worker language full reload | 2026-07-02 |
| #21 | AIR-0118 update work index after docs merge | 2026-07-02 |
| #20 | AIR-0118 preserve longform validation docs | 2026-07-02 |
| #19 | AIR-0119 centralize AI provider routing | 2026-07-02 |
| #18 | AIR-0117 project status synchronization after merged PRs | 2026-07-02 |
| #17 | Fix auth-web lint execution and warnings | 2026-07-02 |
| #16 | Add per-feature AI model settings | 2026-07-02 |

### Open PRs
| PR | Title | Status / Action |
|----|-------|-----------------|
| air-0129 | AIR-0129 admin auto-translation pipeline | OPEN — depends on PR #31; requires both migration SQLs applied |
| #31 | AIR-0128 DB-persistent topic translation | OPEN — requires migration SQL approval + product owner review |
| #30 | AIR-0126 project status document sync | OPEN — awaiting product owner merge |
| #29 | AIR-0125 document referral migration runbook | OPEN — awaiting product owner review before merge |
| #28 | AIR-0124 add manual referral payout processor | OPEN — awaiting product owner review before merge |
| #27 | AIR-0123 add referral settlement pending worker | OPEN — awaiting product owner review before merge |
| #26 | AIR-0122 implement referral default sponsor foundation | OPEN — includes DB migration; awaiting CTO approval before merge |
| #22 | AIR-0119 finalize work index | OPEN — diverged from main (behind 9 commits); content superseded by AIR-0126; recommend close |
| #8 | AIR-0109 connect 2x2 crop output to scene assets | OPEN — superseded by AIR-0110A (PR #9); recommend close |
| #7 | AIR-0108 add longform scene asset review | OPEN — superseded by AIR-0110A (PR #9); recommend close |
| #6 | AIR-0107 validate and harden longform media upload pipeline | OPEN — superseded by AIR-0110A (PR #9); recommend close |
| #5 | AIR-0106 audit longform production pipeline | OPEN — superseded by AIR-0110A (PR #9); recommend close |
| #4 | AIR-0106 organize longform prompt architecture | OPEN — superseded by AIR-0110A (PR #9); recommend close |
| #3 | AIR-0105 provider-aware longform AI routing | OPEN — superseded by AIR-0110A (PR #9); recommend close |
| #2 | AIR-0104 validate longform script-plan access | OPEN — superseded by AIR-0110A (PR #9); recommend close |
| #1 | AIR-0102 document longform user flow | OPEN — superseded by AIR-0110A (PR #9); recommend close |

## Task Pointer
Latest completed task: `AIR-0128` (DB-persistent translation, PR #31 open)
Next available task ID: `AIR-0129`

## Current Priority
1. Keep AIR Studio execution focused on `Longform Mode` completion.
2. Treat `Longform Music`, `General Shorts`, and `Shorts Commerce` as deferred modes.
3. PR #26–#29 (referral system) require separate product owner / CTO approval before merge — do not merge without explicit instruction.
4. PR #31 (AIR-0128) requires product owner review + Supabase migration approval before merge.

## Longform Finish Priorities
1. ~~Language-switch runtime translation bottleneck~~ — **Resolved by AIR-0128** (DB-persistent translation, PR #31).
   - Remaining: apply migration SQL + run backfill script after PR #31 merges.
2. Clean up Vietnamese worker UX on core longform pages.
   - Vietnamese section in `services/i18n.py` is missing 26 `settings.html` JS i18n keys (noted as follow-up in PR #24)
   - Normalize labels through `t()`
   - Remove ad hoc language branching in core worker UI
3. Normalize the longform worker state contract.
   - Define canonical project-status ownership from claim through export
   - Reduce UI-only stage inference where backend-owned status is required
4. Authenticated browser verification of the full Longform worker flow.
   - crop → upload → readiness → render-gate flow not yet browser-verified with dedicated test credentials
5. Simplify payout/withdrawal identity.
   - Remove or hide wallet-address-centered UX
   - Evaluate enforcing Binance ID as payout identity instead of arbitrary wallet addresses
   - Unify duplicated withdrawal endpoints and payload shapes
6. Reduce web-admin startup load.
   - Admin app loads too much data eagerly on startup
   - Polls render queue every 3 seconds
7. Finish project-aware longform/music route separation.
   - `/script-plan` is fixed; audit and fix the rest of the page family

## Open Questions for Product Owner
1. Should PR #22 (AIR-0119 finalize work index) be closed? It is diverged and superseded by AIR-0126.
2. Should PRs #1–#8 (superseded by AIR-0110A / PR #9) be closed?
3. Which Longform Finish Priority above is the next Sprint target?
4. What is the merge timeline and approval process for PR #26–#29 (referral/payout system)?
5. PR #31 (AIR-0128): approve migration SQL + merge when ready. Apply migration before or immediately after deploy.

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
7. Do not merge PR #26–#29 (referral/payout/DB migration) without explicit product owner / CTO approval.

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
- `services/ai_router.py`
- `services/web_admin_client.py`
- `auth-web/components/DashboardContent.tsx`
- `docs/LONGFORM_USER_FLOW.md`

## Notes
- The repo has both AIR Studio runtime code and `auth-web` admin code.
- AIR Studio has four product modes, but only `Longform Mode` is an active completion target right now.
- `Longform Music`, `General Shorts`, and `Shorts Commerce` should remain structurally intact while staying outside the current active build scope.
- Per-feature AI model selection (PR #16) uses model-name-based provider auto-selection via `services/ai_router.py`. Do not break this structure.
- ElevenLabs voice management and longform preview lock are live (PR #14).
- `main.py` uses multiprocessing; a restart must terminate both the parent and its serving child or the old child can keep port 8001 alive.
- PR #26 includes a DB migration (`migration_referral_2.0.sql`). Do not execute migration without explicit approval and runbook review (PR #29).
