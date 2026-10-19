# ElevenLabs v4 integration and sample verification (2026-10-19)

The subtitle editor offers Multilingual v2 and Eleven v4. The selected model is sent to segment synthesis, full narration and the existing browser fallback. Memory and stored audio caches distinguish models. Successful narration finalization saves `tts_model_id` in the project so reopening restores the choice. Existing projects default to v2. Explicit v4 requests fail visibly rather than substituting v3/v2.

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
