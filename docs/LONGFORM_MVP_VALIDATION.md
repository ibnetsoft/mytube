# LONGFORM MVP VALIDATION

## Scope

Task: `AIR-0111`

Date: `2026-07-01`

This review evaluates the Longform worker journey as a service, not as a
collection of isolated screens. Longform Music, General Shorts, and Shorts
Commerce are outside this validation.

## Executive Decision

**MVP open decision: Not ready for external Beta.**

AIR-0112 resolved the first blocker by adding canonical backend Scene readiness
and render gating. External Beta remains blocked until the authenticated browser
flow is repeatable and the complete upload/review/export journey is verified.

The core production pieces exist and the focused Longform tests pass, but the
product does not yet have one backend-owned definition of `assets_ready` or
`project_complete`. A project can be marked rendered or done independently of
the new external-asset review contract. The worker can therefore reach a
terminal-looking state while Scene assets are incomplete.

The recommended next step is not another broad feature. AIR-0112 should define
and enforce the canonical Longform readiness and completion state contract.

## Validation Evidence

- PR #9 (`AIR-0110A`) was merged into `main` at `f5905d07`.
- Latest `origin/main` was checked out in a clean worktree before AIR-0111.
- Latest server health returned HTTP 200 on port 8001.
- Browser reached `/login` and rendered the worker login form.
- Browser validation past login was not performed because no test password was
  supplied and saved credentials were not reused.
- Focused Longform suite:
  - `29 passed`
  - project/music route separation
  - Scene asset matcher
  - Scene asset review
  - 2x2 crop import
- Full test directory:
  - `42 passed`
  - `1 failed` during collection because `pytest-asyncio` is not installed for
    `tests/test_subtitle.py`
  - the failing subtitle file is an external-service script rather than an
    isolated deterministic test
- Actual shared SQLite data was inspected:
  - completed/rendered Longform projects exist
  - project 195 is `rendered` while only 2 of 11 Scenes have any active visual
    asset
  - project 256 retains claimed topic metadata, locked 15-minute duration,
    `$4` payout, `news` script style, and `cinematic` image style

## End-to-End Status

| # | Stage | Status | Evidence | Problem / TODO |
| --- | --- | --- | --- | --- |
| 1 | Sign up / login | Partial | Login page, verification service, and admin-backed membership exist. Browser rendered `/login`. | No dedicated E2E test account or automated login fixture. Signup depends on the web admin. |
| 2 | Recommended Topic query | Implemented with operational dependency | `/api/user/recommended-topics` reads Supabase, applies worker preferences, policy, and cache. Previously browser-verified under AIR-0099/AIR-0103. | Requires Supabase and can be slowed by translation/provider failures. |
| 3 | Topic Claim | Implemented | `/api/user/claim-topic` resolves cached IDs, claims the queue row, and accepts Supabase 204. | Claim and local project creation are not transactional across Supabase and SQLite. |
| 4 | Project creation | Implemented | Claim persists mode, language, locked styles, duration, payout, and queue identifiers. | Rollback is missing if remote claim succeeds but local creation fails. |
| 5 | Script Plan | Implemented | `/script-plan` uses the selected project's mode and redirects music projects correctly. | Other page families still contain global-mode routing shortcuts. |
| 6 | Script Generation | Partial | `/script-gen`, script save/load, and generation paths exist. Saved script restores after refresh. | External AI availability, spend caps, and long-running failure recovery are not covered by deterministic E2E tests. |
| 7 | Automatic Scene creation | Partial | Script save/analyze and `image_prompts` persistence create ordered Scene rows. | Scene identity can be regenerated or renumbered after assets exist; immutable Scene ownership is not enforced. |
| 8 | Image Prompt generation | Implemented | Project Scene prompts are stored in `image_prompts`; prompt review is available on `/image-gen`. | Legacy direct image-generation controls remain visible despite the external-generation operating model. |
| 9 | Video Prompt generation | Partial | Motion/Flow prompt fields and endpoints exist and are displayed with Scene review. | There is no single required, batch-verified video-prompt completion contract for every Scene. |
| 10 | External image generation | External/manual | AIR Studio exposes prompts for use in external AI tools. | Provenance and external-tool metadata are not recorded. |
| 11 | 2x2 image crop | Implemented, browser check pending | `/image-crop` maps four panels to deterministic Scene destinations and safe empty-slot imports. Tests pass. | A real authenticated browser import has not been completed after integration. |
| 12 | External upscaling | External/manual | `scene_NNN_upscaled` filenames reconnect through filename-first matching. | Intentional replacement has no version history or rollback. |
| 13 | External Video AI | External/manual | Scene video prompts and deterministic filenames support the external workflow. | No provenance, retry, or version history. |
| 14 | Video upload | Implemented with scale limits | Bulk image/video upload and per-Scene replacement exist. | Large videos are read fully into memory; no resumable upload or per-file progress. |
| 15 | Scene automatic matching | Implemented | Filename-first matching, validated AI fallback, range checks, occupied-slot protection, and duplicate reporting pass tests. | Stored unmatched assets have no assignment board or cleanup workflow. |
| 16 | Scene Review | Implemented with policy gap | Scene prompt/image/video review, missing status, clip ordering, replacement, and refresh restoration exist. | Readiness currently accepts image or video per Scene; final policy is undecided and UI-owned. |
| 17 | Project completion | Blocking | Render, publishing, and upload status paths exist. | No canonical backend transition connects Scene readiness to render/export completion. Existing project status can contradict Scene asset completeness. |

## Blocking Issues

### B0-1: No canonical Longform readiness/completion state

Status: **Resolved in AIR-0112 for Scene Review, project APIs, and render
entry.** Admin publish/export still needs browser-level validation.

- `assets_ready` is calculated in the UI, not persisted as backend-owned state.
- The required media rule is undecided: image-only, video-only, or both.
- Render/export paths do not enforce the same Scene readiness rule.
- Historical SQLite state proves that `rendered` does not guarantee complete
  Scene assets under the new workflow.

### B0-2: External-asset workflow and legacy internal-generation flow coexist

- Longform workers are intended to create images and clips externally.
- `/image-gen`, `/video-gen`, and `/render` still expose legacy generation and
  render assumptions.
- The primary worker path is not visually or contractually unambiguous.

### B0-3: No repeatable authenticated browser E2E fixture

- Browser validation currently depends on a real worker login.
- There is no isolated Beta test account/fixture and no deterministic Supabase
  test queue.
- Critical claim-to-completion checks cannot be run safely in CI.

## Structural and UX Problems

1. Topic claim spans Supabase and SQLite without compensation.
2. Several worker pages still derive mode from global settings instead of the
   selected project.
3. Translation on language switch remains expensive and provider-dependent.
4. Scene identity is not immutable after asset production begins.
5. Unmatched files are stored but cannot be assigned from a dedicated board.
6. Large video imports lack chunking, retry, and byte-level progress.
7. Asset replacement lacks history and rollback.
8. The full pytest suite is not green because its async test dependency and
   external-service test design are incomplete.

## Improvement Priority

### P0 - Required before Beta

1. Define backend-owned `assets_ready` and `project_complete`.
2. Decide the minimum required Scene asset policy.
3. Enforce the same policy in Scene Review, render, export, and project cards.
4. Add an authenticated Longform E2E fixture with deterministic topic data.
5. Browser-verify one real claim-to-Scene-review journey on the integrated code.

### P1 - Required for reliable worker operation

1. Make selected-project mode authoritative on all Longform pages.
2. Present external prompt/export/import as the primary UI path.
3. Add manual assignment for stored unmatched assets.
4. Add upload retry/progress and practical batch limits.
5. Make Scene identifiers stable once media is attached.

### P2 - Beta hardening

1. Cache recommendation translations and reduce language-switch latency.
2. Add asset provenance and replacement history.
3. Replace the legacy async subtitle script with deterministic pytest coverage.
4. Add compensation or reconciliation for partial topic claims.

## Beta Exit Criteria

AIR Studio can be considered Beta-ready when all of the following are true:

- a test worker can complete the 17-stage flow without direct DB repair
- every stage restores correctly after refresh
- one backend contract owns Scene readiness and project completion
- render/export cannot start when the readiness contract fails
- missing, duplicate, invalid, and unmatched assets have visible recovery paths
- the authenticated browser E2E scenario is repeatable
- the deterministic test suite is green
