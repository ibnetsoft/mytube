# ElevenLabs v4 integration and sample verification (2026-10-19)

## New-script vocal performance

New standard scripts receive a local Codex vocal-performance stage after final text and dialogue review. New grounded-console packages receive the same stage when a plan is absent. Existing script repair and project reopening do not run this stage. The stage stores `structure.audio_performance` separately from the immutable spoken script, with exact quote anchors validated into Unicode code-point offsets, a restricted vocal tag set, and contextual reasons. No music or environmental effects are introduced through this channel.

The web maps those cues onto exact matching subtitle text after splitting. Only Eleven v4 synthesis receives bracketed tags; subtitles, translation input and recorded timelines retain plain text. Current delivery is carried into independent clips within a scene. Performance is part of persistent and in-memory audio identity, including repeated lines during assembly. A direction change cannot reuse a plain or differently acted clip. Scripts without plans retain their existing cache identities and recordings. V4 sends Stability/Similarity only; older models retain their existing Style/Speed settings.

## Default update

New generation now defaults to v4, including projects whose prior narration metadata says v2. Opening a project does not generate or migrate audio. The default generation flow reuses existing clips when text, speaker, speed and delivery settings are unchanged, keeping their original model metadata and cache keys. Missing or edited clips use v4. Read-only final assembly can resolve older-model recordings under their existing keys. Explicitly changing the model selector requests that model instead of accepting other-model clips. Google cache identities stay unchanged. Existing finalized narration and its subtitle timeline are not rewritten by this release.

The segment-cache harness was updated for the route's current dependencies and now verifies preview and final assembly reuse a v2 clip with zero synthesis calls and unchanged asset metadata. The browser test verifies v4 is the default even when the project's old recording metadata says v2, and opening the project sends no synthesis requests.

The following records the original optional-model rollout and comparison:

The subtitle editor offers Multilingual v2 and Eleven v4. The selected model is sent to segment synthesis, full narration and the existing browser fallback. Memory and stored audio caches distinguish models. Google/Voice Studio cache identities remain unchanged when the ElevenLabs model changes, preserving reusable narration in mixed-provider projects. Successful narration finalization saves `tts_model_id` in the project so reopening restores the choice. Existing projects default to v2. Explicit v4 requests fail visibly rather than substituting v3/v2.

The configured account's `/v1/models` response included `eleven_v4` with `can_do_text_to_speech: true`. Eight short source clips were generated through the speech-with-timestamps API using Laura (`FGY2WhTYpPnrIDTdsKH5`), two identical subtitle rows per language/model. All used speed 1, stability 0.7, similarity 0.75 and style 0.45, with no emotional tags. Samples are under `_dev/artifacts/elevenlabs-v4-comparison/` (local artifacts, not committed).

| Language | v2 timeline | v4 timeline | Change |
| --- | ---: | ---: | ---: |
| Korean | 12.513 s | 14.890 s | +2.377 s |
| Japanese | 12.931 s | 14.942 s | +2.011 s |

The production `assembleStoredNarration`, `finalizeNarrationMp3` and `applyRecordedSubtitleTiming` functions assembled all four samples and set their subtitles. Browser-reported durations match the saved timeline to the displayed microsecond. Decoded PCM durations are about 12 ms shorter, consistent across all samples. Subtitle windows are contiguous; final spoken letters fall within their windows. Provider v4 punctuation timestamps extend 29–54 ms beyond frame-derived clip durations; these provider timestamps are diagnostic only and are not used for application subtitle timing.

Old v2 subtitle times must not be reused for v4 recordings. At the second row, old times would switch Korean subtitles about 1.045 s early and Japanese subtitles about 0.940 s early. Finalization recalculates these boundaries from the actual generated recordings.

This is a short-sample timing/compatibility comparison, not a listening-quality verdict or a long-form drift study. Independent transcription was unavailable: the configured API key returned `missing_permissions` for `speech_to_text`. Listen to both versions in `comparison.html` before choosing a preferred delivery.

## Reproduce

Set `FFMPEG_PATH` to an installed FFmpeg executable, then run from the repository root:

```powershell
node scripts/compare_elevenlabs_v4.cjs
node scripts/verify_elevenlabs_v4_samples.cjs
node scripts/serve_elevenlabs_comparison.cjs
```

Generation reuses local cached samples. The verification script also caches transcript attempts, including unavailable-permission results. The comparison player is at `http://127.0.0.1:3018/comparison.html` and supports byte-range audio seeking.

Validation: production Next.js build; 20 TTS feedback tests; recorded subtitle timing tests; stored narration tests; strict v4/no-downgrade/cache-isolation tests; browser model selector/request/reopen/error flow; and real sample duration, character-boundary and browser seeking checks. The older segment-cache test harness cannot load the current route's `@/lib/stdAudioAnchors` dependency; it was not changed for this feature.

Direct Vercel project access returned HTTP 403 and the CLI scope lookup also failed. The repository's connected `main` branch is the deployment path for this change; verify its GitHub Vercel status after pushing.
