# Next Tasks

## Completed This Sprint
- AIR-0213: Scene pipeline E2E tests + Unmatched asset board — DONE
- AIR-0214: Windows installer + atomic-swap updater — DONE (PR #67)
- AIR-0215: Windows updater hardening — DONE (PR #67)
- AIR-0216: Release pipeline automation — DONE
- AIR-0218: GitHub Actions release automation — DONE (same branch as AIR-0216)

## Pending: Real-install E2E QA
- AIR-0217: `project_status/QA_AIR_0215_E2E.md` — 8 scenarios, requires test machine

## Pending: PR Merges
- PR #67 (AIR-0214/0215) — CTO approved, ready to merge
- AIR-0216/0218 PR — to be created after PR #67 merges

## Next Sprint Candidates

1. **Canonical export contract** (KI-001) — AIR-0219
   Define and enforce a single export delivery path.
   Multiple paths (render/export/download) are uncoordinated.

2. **Authenticated browser E2E fixture** (KI-003)
   Full Longform worker journey with test credentials.
   Login → Claim → Script → Prompts → Upload → TTS → Render check.
   Requires Playwright setup + Supabase test account.

## Reference
- `BOOTSTRAP.md` — installer/updater system spec
- `RELEASE_PROCESS.md` — full release workflow (manual + CI)
- `QA_AIR_0215_E2E.md` — 8-scenario real-install E2E QA checklist
- `KNOWN_ISSUES.md` — issue list with priorities
