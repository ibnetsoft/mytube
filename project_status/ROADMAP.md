# ROADMAP

## Objective
Turn AIR Studio into a repo with durable project memory so future Codex/ChatGPT sessions can resume work from git + local docs instead of relying on chat history.

## Product Direction
- `Longform Mode` is the primary delivery target and should receive active implementation effort first.
- `Longform Music`, `General Shorts`, and `Shorts Commerce` should remain structurally safe but are not current feature-delivery priorities.
- The existing BFF-oriented organization should be preserved and clarified as we continue longform work.
- ChatGPT/Codex planning should route proposed work through the `Longform Mode first` rule before adding active implementation scope.

## Phase 1: Project Memory Bootstrap
- [x] Create `project_status` and `worknote` handoff docs
- [ ] Establish the default read order for future sessions
- [ ] Document core runtime domains and critical files
- [ ] Capture current active issues and short-term priorities

## Phase 2: Longform Mode Completion
- [x] Verify topic claim API -> project creation
- [x] Verify topic card click -> browser page redirect for `longform`
- [x] Document current longform worker flow from login to export
- [x] Audit the real external-AI production pipeline from scenes and prompts through imported media
- [x] Add deterministic and non-destructive scene asset import validation
- [x] Add scene asset review, final clip ordering, and missing-visual gating
- [x] Connect 2x2 crop output to project scene ownership
- [x] Validate the complete Longform MVP journey and record Beta blockers
- [ ] Persist canonical Longform Scene readiness and project completion
- [ ] Enforce readiness consistently in review, render/export, and project cards
- [ ] Add a deterministic authenticated Longform browser E2E fixture
- [ ] Finish worker-facing longform topic selection and project boot flow
- [ ] Remove language-switch latency from worker-facing pages
- [ ] Stabilize saved or cached translation strategy for recommendation cards
- [ ] Verify translated topic display in `vi/en/th`
- [ ] Clean up Vietnamese/Thai worker UX on core longform screens
- [ ] Add Gemini cooldown / failure suppression for translation-heavy paths
- [ ] Reduce noisy terminal logging for expected fallback cases
- [ ] Simplify payout identity and withdrawal UX for real longform operations

## Phase 3: Domain Documentation
- [x] Document longform user flow and current worker journey
- [ ] Document AIR Studio runtime architecture
- [ ] Document `auth-web` admin responsibilities
- [ ] Document policy sync between admin and local app
- [ ] Document data ownership: local SQLite vs Supabase
- [ ] Document mode boundaries: what is shared infrastructure vs what is longform-only
- [ ] Document the final payout identity contract if Binance ID replaces external wallet-address UX

## Phase 4: Deferred Modes Protection
- [ ] Keep `longform_music` routing/schema assumptions isolated from `longform`
- [ ] Prevent `general_shorts` and `shorts_commerce` placeholders from blocking longform delivery
- [ ] Record missing contracts required before deferred modes are resumed

## Phase 5: Operational Discipline
- [ ] Standardize handoff update flow after each major task
- [ ] Keep `KNOWN_ISSUES.md` current
- [ ] Use focused commits that map cleanly to runtime or domain changes

## Suggested Read Order For Future Sessions
1. `project_status/NEXT_TASK.md`
2. `project_status/LATEST.md`
3. `worknote/latest.md`
4. `project_status/KNOWN_ISSUES.md`
5. Relevant code files
