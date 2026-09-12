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
