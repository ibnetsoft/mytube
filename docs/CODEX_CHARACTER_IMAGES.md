# Codex character reference images

The staged worker now requires this order:

1. Plan and write the script; pass independent senior narration review.
2. Finalize the principal cast from that exact script (one lead, up to two supporting characters).
3. Use the Codex CLI's **built-in image_gen tool**, not an image API or Gemini, for one reference PNG per character.
4. Inspect and validate real PNGs, upload versioned objects to `content-assets/topics/<topic>/characters/`, check anonymous access and byte hashes, and read back `topic_character_assets`.
5. Pass the references and character descriptions into scene image prompts and the first twelve video prompts. No video clips are generated.
6. Store references in the content package and queue structure. Claims inherit them. Already-active projects are linked only when their script exactly matches; submitted or edited projects are preserved.

The STD image page shows a separate character-reference panel. Missing images are labelled as missing, never completed based on text alone.

The scene exporter requires real character reference images. It downloads them beside its manifest and lists the exact reference files to attach to every built-in scene-grid generation. It does not create video clips. Existing scene generation remains the CoWork grid workflow; this change does not silently regenerate old topics or their scene images.

## Failure and recovery

- Missing native image tool, missing character DNA, malformed PNG, failed upload/readback or private/unreadable object stops the job before media prompt generation.
- There is no Gemini/image API fallback and no manual approval is fabricated.
- Native image results are cached by prompt/version with verified PNG hashes; successful uploads use content-addressed filenames to preserve old references.
- A successful portrait is not evidence that scene images or a final video exist.
- Existing-script repairs that intentionally modify only narration do not automatically re-run image generation. Run a scoped character reference backfill separately when needed.

Tests: `python -m pytest tests/test_codex_content_runner.py tests/test_codex_character_assets.py -q`.
The worker process must load the updated Python module (restart when idle); packaged Windows builds include the new module. Web changes require the normal auth-web deployment.
