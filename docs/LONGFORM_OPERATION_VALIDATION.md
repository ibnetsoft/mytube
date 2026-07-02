# LONGFORM OPERATION VALIDATION

## Task
- AIR-0118

## Purpose
- Validate whether a real operator can complete the current `Longform Mode` production workflow.
- This is an operational validation task, not a feature-development task.
- Scope is limited to `longform` only.
- `longform_music`, `general_shorts`, and `shorts_commerce` are out of scope.

## Validation Constraints
- No safe login-capable test credentials were available in this session.
- Because the worker login could not be completed safely, browser execution of the real operator flow was blocked.
- Where browser execution was blocked, this document records:
  - `BLOCKED`
  - why it was blocked
  - substitute evidence from code, pytest, API contracts, and prior validated records

## Current Gate Summary
- PR #11 merged into `main` at `0431b723`.
- Canonical Longform `assets_ready` policy is backend-owned under `image_or_video`.
- Focused Longform readiness tests pass.
- Render is blocked with HTTP 409 when `assets_ready=false`.
- Admin publish/export paths still need authenticated browser-level validation.

## Focused Test Evidence
- Command:
  - `python -m pytest --basetemp=.pytest-tmp tests/test_longform_asset_readiness.py tests/test_scene_asset_matcher.py tests/test_scene_asset_review_ui.py tests/test_scene_crop_import_ui.py`
- Result:
  - `16 passed, 1 warning`

## Workflow Validation Matrix

| Step | Stage | Status | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 1 | Login | BLOCKED | No safe test credentials in this session. `docs/LONGFORM_USER_FLOW.md` documents `/login` and prior browser reachability. | Real operator login must be rerun with dedicated credentials. |
| 2 | Topic selection | BLOCKED | Prior AIR-0099/AIR-0103 browser validation plus `GET /api/user/recommended-topics` implementation documented in `docs/LONGFORM_USER_FLOW.md`. | Depends on authenticated worker session. |
| 3 | Project creation | BLOCKED | Prior validated claim-topic flow; local project creation is documented and previously browser-verified. | Depends on Step 2. |
| 4 | Script plan generation | BLOCKED | `/script-plan` is documented and project-aware for `longform`. | Needs authenticated run on a real claimed project. |
| 5 | Script generation | BLOCKED | Script generation route exists in current Longform flow docs. | Needs browser/runtime execution with project context. |
| 6 | Scene split | BLOCKED | Longform flow docs describe scene/media preparation after script generation. | Needs real project execution. |
| 7 | Scene image prompt generation | BLOCKED | `image-gen` flow exists and is documented in current Longform pipeline docs. | Needs authenticated project run. |
| 8 | Scene video prompt generation | BLOCKED | Motion/video prompt fields and flow are documented in Longform flow/MVP validation docs. | Needs authenticated project run. |
| 9 | External AI 2x2 image generation | BLOCKED | External manual step by design; AIR Studio does not generate these assets itself. | Needs operator-provided external outputs. |
| 10 | AIR Studio image crop | BLOCKED | `/image-crop` route, deterministic scene destinations, and crop/import tests are implemented and passing. | Browser import with real assets still not run in this session. |
| 11 | Scene slot check | BLOCKED | Scene Asset Review UI shows per-scene Image/Video readiness columns and completion percentage. | Real browser verification blocked. |
| 12 | External upscaling | BLOCKED | External manual step by design. | Requires operator-provided outputs. |
| 13 | External Video AI | BLOCKED | External manual step by design. | Requires operator-provided outputs. |
| 14 | Video clip generation | BLOCKED | External manual step by design. | Requires operator-provided outputs. |
| 15 | Video upload | BLOCKED | Upload/matching flow is implemented and documented; focused matcher/crop UI tests pass. | Real authenticated upload not run in this session. |
| 16 | Scene auto placement | BLOCKED | `POST /api/image/bulk-match` returns matched / duplicates / unmatched / invalid / missing scene data; matcher tests pass. | Browser verification blocked. |
| 17 | Scene Review | BLOCKED | Scene Asset Review UI exists and displays prompt/image/video status, missing scenes, clip order, and completion bar. | Browser verification blocked. |
| 18 | Scene approval | BLOCKED | Continue-to-TTS control is gated by canonical readiness state in the UI. | Browser verification blocked. |
| 19 | `assets_ready` check | PASS | Backend-owned policy in `services/longform_asset_readiness.py`; focused readiness tests pass; project/API/template wiring exists. | Verified by code/tests/API contract, not browser. |
| 20 | Export availability check | BLOCKED | Render blocking is enforced when incomplete; admin publish/export routes exist. | Real operator export/publish path remains browser-blocked and needs follow-up. |

## Admin Validation Matrix

| Area | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Admin Publish request | BLOCKED | `POST /api/projects/{id}/admin-publish-request` exists; worker export docs say standard workers should use web-admin publishing registration. | Needs authenticated browser/admin execution with a rendered project. |
| Export path | BLOCKED | Longform flow docs show `/video-upload?project_id={id}` and admin publish path; code contains worker restrictions and publish/upload branching. | Needs real rendered artifact and authenticated worker/admin flow. |
| Readiness Gate | BLOCKED | Longform render blocks on `assets_ready=false` with HTTP 409. Admin publish/export still needs end-to-end validation against the same readiness expectation. | Browser/admin proof still missing. |

## Known Failures / Blockers

### BLOCKER-001 — Safe test credentials missing
- Priority: P0
- Status: Open
- Affected stages:
  - Login
  - Topic selection
  - Project creation
  - All downstream browser workflow stages
  - Admin/browser publish-export validation
- Cause:
  - No dedicated operator test account or safe credential handoff was available in this session.
- Reproduction:
  1. Start Longform operational validation.
  2. Reach the login requirement.
  3. Attempt to continue without a dedicated approved worker account.
  4. Validation halts because safe authenticated execution cannot proceed.
- Recommended fix:
  - Provision a dedicated approved test worker account and, if needed, a paired admin validation account.

### GAP-001 — Admin publish/export still lacks end-to-end validation evidence
- Priority: P1
- Status: Open
- Cause:
  - The code paths exist, but authenticated browser/admin proof was not completed in this session.
- Reproduction:
  1. Complete a Longform project to rendered state.
  2. Attempt admin publish registration / export using the intended worker path.
  3. Observe that current evidence is code/documentation-based rather than fresh browser proof.
- Recommended fix:
  - Run AIR-0119-style follow-up with dedicated worker/admin test accounts and a rendered fixture project.

## Operational Judgment
- Current code and focused tests support the canonical Longform readiness contract.
- The critical missing evidence is not implementation of `assets_ready`; it is authenticated operational proof of the full worker and admin publishing workflow.
- Therefore:
  - Longform readiness enforcement is validated.
  - Full real-operator workflow execution is not yet fully validated.

## Result Summary
- Worker browser flow: `BLOCKED`
- Longform readiness contract: `PASS`
- Render gate when incomplete: `PASS`
- Admin publish/export operational proof: `BLOCKED`

## Recommended Next Action
1. Provision dedicated Longform worker test credentials.
2. Provision admin-side validation access if separate from the worker account.
3. Re-run the 20-step scenario with real external assets.
4. Capture PASS / FAIL / BLOCKED per step with screenshots or route/API evidence.
5. Confirm admin publish/export honors the intended readiness gate and standard-worker restrictions.
