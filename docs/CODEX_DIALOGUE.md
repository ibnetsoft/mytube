# Astra script and dialogue annotations

The active Codex staged content worker pins script writing, rewriting, independent
review and final dialogue analysis to `gpt-6-astra`. A configured general content
model does not override these stages. No model fallback or speech-detection regex
is used. Stage caches include the model and instruction revision.

After the final rewrite, Astra reads the complete script and cast and returns
exact spoken substrings, speakers, occurrence numbers, evidence and uncertainty.
Code checks only schema and exact source positions; it does not decide what is speech.
Malformed annotations stop generation after bounded retry rather than marking
the package ready with guessed dialogue.

`structure.dialogue_annotations` stores source text, SHA-256, Unicode-codepoint
offsets, model and annotation status. It travels with the existing package and
`pregenerated_structure` into the claimed project's `project_payload.structure`;
no additional database columns are required.

The subtitle page aligns every scene's complete subtitle text to the stored source
(ignoring subtitle whitespace/quote formatting only). Confirmed spoken characters
are yellow and show their speaker in a tooltip. Uncertain spans are saved but not
highlighted. Missing/stale annotations never fall back to quote/verb guessing.
Mixed narration/dialogue blocks are split at confirmed AI boundaries on loading,
scene synchronization and saving. Speaker changes also create separate blocks.
Splitting preserves the exact concatenated text, scene/media and parent time span;
fragment durations are proportional text allocations, not forced audio alignment.
Old whole-block audio links are removed from new fragments and require regeneration.
Repeated splitting is idempotent. Manual merge permits only narration with narration,
or dialogue from the same speaker. Missing/stale annotations do not trigger guessing.

Existing scripts are not rewritten or re-annotated by deployment. They need a
separate AI annotation run before yellow dialogue marks are available. Restart
the local worker to load Python changes and deploy the web changes for user access.
