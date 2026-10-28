# Codex character reference images

The staged worker now requires this order:

1. Plan and write the script; pass independent senior narration review.
2. Finalize the principal cast from that exact script (one lead and every recurring supporting character, without a fixed cast cap).
3. Use the Codex CLI's **built-in image_gen tool**, not an image API or Gemini, for one reference PNG per character.
4. Before accepting each new portrait, compare actual pixels against every other saved/current character in the same topic using the local Codex CLI. Clothing, hair, wrinkles and pose do not establish a separate face: require at least three substantial structural differences among face shape, eyes, nose, mouth, jaw and proportions. Similar/uncertain candidates receive at most two face-only repair generations; refusals or generation failures are not automatically retried. A failed candidate is never published. Reused saved portraits must also pass; similar existing approved faces stop preflight for explicit cast repair instead of silently changing established scene identities.
5. Inspect and validate real PNGs, upload versioned objects to `content-assets/topics/<topic>/characters/`, check anonymous access and byte hashes, and read back `topic_character_assets`.
6. Pass the references and character descriptions into scene image prompts and the first twelve video prompts. No video clips are generated.
7. Store references in the content package and queue structure. Claims inherit them. Already-active projects are linked only when their script exactly matches; submitted or edited projects are preserved.

The STD image page shows a separate character-reference panel. Missing images are labelled as missing, never completed based on text alone.

The scene exporter requires real character reference images. It downloads them beside its manifest and lists the exact reference files to attach to every built-in scene-grid generation. It does not create video clips. Existing scene generation remains the CoWork grid workflow; this change does not silently regenerate old topics or their scene images.

## Failure and recovery

- Missing native image tool, missing character DNA, malformed PNG, failed upload/readback or private/unreadable object stops the job before media prompt generation.
- There is no Gemini/image API fallback and no manual approval is fabricated.
- Native image results are cached by prompt/version with verified PNG hashes; successful uploads use content-addressed filenames to preserve old references.
- A successful portrait is not evidence that scene images or a final video exist.
- Existing-script repairs that intentionally modify only narration do not automatically re-run image generation. Run a scoped character reference backfill separately when needed.

Tests: `python -m pytest tests/test_codex_content_runner.py tests/test_codex_character_assets.py -q`.
The worker process must load the updated Python module (restart when idle); the retired Windows installer is not a release target. Web changes require the normal auth-web deployment.

The final cast is audited again against the complete set (including characters generated later). Each saved `face_distinctness_review` binds actual candidate and peer image SHA-256 values, observed facial differences and the policy version. Missing or stale comparisons cannot use the recurring-character preflight ready cache. Scene prompts carry these structural observations and explicitly forbid cloning a face with a changed hairstyle or costume. This is qualitative visual review, not a biometric similarity percentage.
