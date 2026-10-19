# Motion Studio automatic submission modes

The active product is `auth-web/`. The user supplies scene originals and finalized recorded audio, saves a production mode, and submits. Manual keyframes are optional advanced controls, not required input to automatic production.

## Modes

- `ae_only`: PSD layers use native After Effects; image/video scenes use the deterministic local compositor. No video-generation provider is loaded or called. Background-only still inpainting can remain part of PSD preparation.
- `hybrid`: the same pipeline, with optional short inserts through the settings-selected fal or Replicate model. The submitted model ID and configuration fingerprint are frozen. At most 1–3 inserts, at most 3–5 seconds each, and at most 20% of the complete recording. The director may choose no insert. Provider/model input compatibility still requires live validation with a real configured model.

Both support 16:9 and 9:16. Vertical webtoon originals default to 9:16. No page-turn transition is introduced.
Existing manually produced clips remain valid inputs without a generation API. Automatic source selection prefers an original PSD, then an existing video for ordinary projects; vertical webtoons prefer original images. Explicit advanced source selections are respected.

## Execution and review

1. Submission validates the recorded narration identity and exact subtitle timing, selects stored originals, resolves sound cues, and seals the immutable snapshot. No prior manual PSD preparation or camera-key editing is required.
2. The local media supervisor claims `motion_automation` serially with other heavy media jobs. Local Codex CLI receives actual original/neighbor images and a decoded final-audio waveform, transcript, and immutable timing. Waveform/PCM inspection does not claim listening.
3. PSD preparation inspects real separated layers, validates their reconstruction, and runs native AE. Flat images/videos use bounded camera and overlay motion. Unsupported required anatomy/motion escalates instead of inventing body parts.
4. Each produced scene is checked against the original and predecessor, using actual sampled frames, measurements from every decoded frame, and independent decoded audio comparison. A deterministic scene can be redirected and rendered once more after a failed review. Generated inserts are never automatically regenerated after failed review.
5. Assembly restores the final full recording, captions, saved template, BGM and SFX. Another actual-frame/caption/boundary review checks the complete output.
6. A service-only atomic completion transaction stores the reviewed video asset, existing render-history entry and administrator-review receipt together. It does not approve publishing or upload to YouTube.

Existing explicitly enabled lip-sync must already have a matching reviewed lip-sync asset; this change does not silently generate or bypass lip-sync. A final recording with no aligned/validated timing is rejected, rather than guessing speech timing.

## Recovery and paid requests

Frozen input and worker-lease fields cannot be overwritten by progress updates. Heartbeats merge atomically with provider checkpoints. Local reviewed artifacts are reused only with matching input, source preview, audio and output hashes. Closed projects stop production.

Before a paid provider POST, the web proxy commits a creation-intent checkpoint. An ambiguous response becomes `needs_reconcile`; retrying cannot create another paid request. Resuming a confirmed request polls its existing ID. A changed plan or submitted model configuration blocks reuse. API keys stay encrypted server-side and are never copied into snapshots or worker metadata.

`node scripts/std_continue_submission.cjs PROJECT_ID [--enqueue]` reports automatic jobs without sending them through the legacy mouth renderer or registering duplicate renders.

## Verification and remaining rollout

- TypeScript checks, production web build, focused Node/Python tests and rollback-only production database contract checks are required.
- `tests/std_motion_pipeline.sql` tests ownership, idempotent registration, immutable fields, leases, review-gated atomic completion and unchanged administrator approval. All fixture rows are rolled back.
- `worker/motion_automation_smoke.py NAME` exercises actual local Codex direction, deterministic 1080p rendering, audio preservation, and actual-output review with a synthetic original and finalized calibration tone. This is not native AE, customer narration, a production queue submission or a customer-quality sample.
- Paid live video generation is deferred at the user's request. Provider HTTP contracts are tested with mocked responses.
- Updating/restarting the office Windows supervisor and verifying the new production queue through native AE are deferred until the office session, at the user's request. A web deployment alone does not update that running process.

Recorded local evidence: `output/codex-local-console/motion-automation-smoke/auto-two-modes-20261019-c/report.json` and `final/output.mp4`. Actual local Codex direction, scene review and assembled-output review passed. The 3-second 1920×1080, 24 fps output has SHA-256 `2bb40cd27e6b48596966d010a2601106fb5b289acd669a7afd3df904c9b619e9`; decoded final audio relative PCM error was `0.00001869185835051435`. This simple synthetic fixture establishes execution, not dramatic quality on customer art. No paid video-generation request was made.

Focused checks: 37 Node tests; 26 motion Python tests and 6 existing supervisor/dashboard checks; TypeScript and Next.js production build. The PSD bridge additionally verifies reviewed local layer hashes/canvas and supplies the native renderer's layer-path map; this is unit-tested, not an office AE execution claim. Both new migrations were applied and the rollback-only database test passed. This is not an all-repository test-suite claim: legacy `std-submit-ae-resubmit.cjs` fixtures still reject existing `stdSubmissionPipeline` imports and were not rewritten as part of this change.
