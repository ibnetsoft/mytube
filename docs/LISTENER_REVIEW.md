# Listener quality gate (listener_v1)

Runs after senior continuity QA and before dialogue annotation, character images,
media prompts and publication metadata. All 02* stages retain the Astra model pin.

1. Two fresh text-only listener reviews: naturalness and engagement. The input
   allowlist contains only title and final scene texts; no plans, author scores,
   cast explanations, previous criticism or self-evaluations.
2. Every finding must cite an exact substring and existing scene number, explain
   listener impact and propose a local fix. Passing requires no unresolved issues.
   Quiet pacing is not itself a defect and sensationalism is not rewarded.
3. At most one revision round, editing only flagged scenes within existing timing
   budgets. Unflagged text, ordering and scene count are preserved in code.
4. Randomized A/B comparison receives neither revision labels nor review findings.
   One dimension must improve; neither may worsen; regressions must be empty.
   A tie does not authorize accepting a revision to a rejected script.
5. Candidate receives fresh listener reviews, followed by the existing independent
   senior continuity/factual review and structural/rhythm checks. Failure stops
   completion before image generation or saving a ready package.

Audit results and the final section hash persist in structure.listener_quality_report.
The existing stage request/response files retain original input, proposed patches,
and comparisons for diagnosis. Rejection does not replace a user's stored script.

This is text review for listening, not real TTS/audio listening or a validated human
audience score. Automated tests verify gating, isolation and preservation, not
creative quality. Real audience-approved good/bad scripts should be accumulated
as a separate held-out evaluation corpus; do not label synthetic fixtures as
measured senior-audience preference. No TTS generation or user-data backfill is
triggered by this change. Restart the worker to load updated Python modules.

## User-approved comparison example and incremental revisions

The user preferred [3197's revised draft](script-revisions/3197-approved-20260912.md)
to its previous version on 2026-09-12. This is one qualitative user preference,
not a measured senior-audience score or an independent listener-gate pass.

Use the example to discuss narrative cause and effect, protagonist agency,
concrete lived experience, a smaller set of meaningful props, and reconciliation
shown through changed behavior. Do not copy its plot, phrases, sentence endings,
scene count, or length into unrelated categories. The blind reviewer must still
receive only the candidate title and script; do not leak this preference as a
hint that it should approve a particular candidate.

For existing scripts, review one identified project, show a full proposed rewrite,
and obtain approval before replacing its saved script. Back up prior data,
preserve scene identities, invalidate outdated audio/annotations, and explicitly
track visual/prompt/metadata dependencies needing revalidation. Do not silently
rewrite other projects sharing a title or mark an approved draft as fully produced.
