# Next Tasks

## Completed This Sprint
- AIR-0213: Scene pipeline E2E tests + Unmatched asset board — DONE
- AIR-0214: Windows installer + atomic-swap updater — DONE (Conditional Approval resolved)
- AIR-0215: Windows updater hardening (all 9 Codex items) — DONE

## Pending: Real-install E2E QA (post-merge)
- See `project_status/QA_AIR_0215_E2E.md` — 7 scenarios, requires test machine with actual install

## Next Sprint Candidates

1. **Canonical export contract** (KI-001) — AIR-0216
   Define and enforce a single export delivery path.
   Multiple paths (render/export/download) are uncoordinated.

2. **Authenticated browser E2E fixture** (KI-003) — AIR-0217
   Full Longform worker journey with test credentials.
   Login → Claim → Script → Prompts → Upload → TTS → Render check.
   Requires Playwright setup + Supabase test account.

3. **Unmatched asset UI polish** (KI-014 follow-up)
   Bulk-assign and sort options.

## Reference
- `BOOTSTRAP.md` — installer/updater system spec
- `QA_AIR_0215_E2E.md` — E2E QA checklist for real-install validation
- `worknote/AIR-0215.md` — AIR-0215 implementation details + remaining risks
- `KNOWN_ISSUES.md` — issue list with priorities
