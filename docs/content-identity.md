# AIR Studio content identity

The active implementation is `auth-web/`. Receipts live in existing JSON
metadata, so no schema migration or replacement of media files is required.

## Identity and ownership

`project_payload.content_identity` identifies the topic, project and immutable
script revision (`sha256:` plus an NFKC, whitespace-normalized content hash).
Saving a changed script records the previous identity and appends a
`std_project_assets` row of kind `content_revision`. The deterministic UUID is
scoped by project and script hash. Existing snapshots are never upserted.
They preserve the actual script, subtitles and structure, rather than only a
version number. Revision receipts describe content, not authorization.

Each new narration, upload, AE mouth job and generated image/video records its
generation input identity. Scene receipts include the stable database scene
ID (when known), project-scoped scene key and visual prompt hash. Derived
mouth videos additionally identify their source image, source video and
finalized audio through parent asset IDs and generation job ID.

Browser upload initialization durably records an `asset_upload_claim` before
issuing the upload URL. Completion reads that receipt; it rejects a changed
script, prompt, type or scene instead of labelling an old upload as current.
TTS captures the starting revision and preserves stale output without attaching
it if the project changed during generation. A compare-and-set protects the
project update; previous audio is retired only after the update succeeds.

## Render gate

The render queue resolves the explicitly selected narration ID; ordering or a
newer timestamp cannot select another recording. Conflicting IDs and multiple
unselected recordings fail. The gate compares every subtitle's text, voice and
recorded time, the script contents, and the recording duration regardless of
whether mouth effects are enabled. A finalized recording suppresses worker
TTS, so rendering cannot silently create a different narration.

Scene media is checked against project/topic, scene ID/number, storage path,
original visual inputs and, for mouth videos, source audio and script revision.
Unchanged visuals can be reused across narration edits when their original
visual input hash matches. Reviewed video tails also retain the original
source path checks and exact scene duration checks.

The immutable render config, queue metadata and asset manifest carry these
identities. The local renderer compares config and queue identities before
downloading. It rejects mismatched scene/topic/audio inputs and verifies
downloaded bytes when a source SHA-256 receipt exists. Publishing remains a
separate action.

## Legacy evidence

`node scripts/std_content_identity.cjs PROJECT_ID` audits without writing.
`--record` backs up current project and asset metadata, then adds receipts
using compare-and-set writes. It neither approves outputs nor changes media.

Old recordings with their own stored transcript can be assigned their actual
recorded-content hash. Old mouth output can inherit the identity of its
explicit source audio. Other old assets are marked `legacy_database_scope`,
with a null script revision; their topic/project/scene links are known but
their birth revision is not. The render manifest retains this limitation.
The audit must never stamp the current script hash onto an unverified old
image. Raw imported narration without a recorded transcript needs an approved
transcript receipt bound to the actual file hash.

Shared BGM/SFX library files may have a different storage owner only when the
asset records its explicit library ID. They must never be selected as narration.

## Checks

Run the content-identity, AE-mouth and render-storage Node tests and
`tests/test_content_identity.py`; then run the web production build. The tests
cover expanded scripts with original audio, stale audio parents, wrong topic
paths, scene mismatches and render-time TTS regeneration.
