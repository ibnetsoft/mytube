# Render quality audit — 2026-09-21

## Inspected render

- Job: `e6082e83-985b-4bf7-a5bc-beeebfe29cce`, render version 5.
- Project: `10b3d223-1457-415a-ba40-7b947c6c1b3d`.
- Completed at 18:52, before the fixes described in the user's 19:17/19:37 history.
- Read-only inspection of its saved config: worker TTS enabled, speed 0.9, 168 synthesis segments, 313 subtitles, five assigned voices. The predominant narrator has 149 segments; the other voices appear in dialogue.
- The first synthesis request ends with “등에 작은”, followed by another request beginning “보따리 하나를…”. Subtitle line breaks were also sent as speech line breaks.
- The old config and queue record establish the requested plan, not whether synthesis succeeded. The temporary synthesis manifest was removed and the job record did not retain success/fallback provenance. Do not claim this job definitely used newly generated ElevenLabs audio.

## Verified defects and fixes

- Running AIRWorker's embedded Python archive lacked `_rounded_ass_path`, despite the source change. A rebuild/restart is required.
- Both worker specs omitted `auth-web/public/fonts`, including the actual Chosun font. Include these assets in both bundle variants.
- ASS opaque boxes are replaced with a single rounded vector contour below the text. Background opacity and stroke remain independent. Actual project settings produced the expected Chosun font selection, rounded corners, and 60% black opacity in an FFmpeg frame.
- Slow zoom used integer crop coordinates and chroma-aligned crop sizes. Replace zoom with cubic perspective sampling of fractional coordinates; keep pans. A two-second, 60-frame centre-of-mass test checks both zoom directions for under 0.15 pixels of centre drift.
- Pause length was stored on shared voice presets, so the last segment overwrote pauses for all occurrences of that voice. Keep it on each segment instead; only terminal punctuation triggers an added pause. Explicit zero remains zero.
- Replace display line breaks with ordinary spaces in synthesis text. Supply previous/next text only across adjacent segments with the same voice. Preserve explicitly selected dialogue voices.
- Send ElevenLabs native speed explicitly; do not apply the same speed again through FFmpeg. Existing explicit saved 0.9 settings remain respected. No duration-based audio stretching is added.
- Persist actual audio source/provider/voice/model/speed in render metadata, including whether submitted audio was used after a synthesis failure.
- Windows manifest renames intermittently failed during tests. Brief bounded retries cover the atomic file rename only; paid synthesis requests are never retried by this change.

## Validation

- 38 relevant tests passed: FFmpeg slideshow, Voice Studio, subtitle synchronization, font assets, narration smoothing.
- Actual 720p zoom sample encoded successfully; actual Chosun font selection checked in libass logs and frame inspected.
- Expanded Drive worker checks: three passed, one pre-existing source-marker assertion failed (`REMOTE_RENDER_DRIVE_DOWNLOAD_ATTEMPTS` absent in HEAD as well). No unrelated download changes made.
- No paid speech generation or full project rerender was performed during this audit. Voice delivery quality still requires listening to a newly generated render; deterministic tests cannot guarantee TTS prosody.
- Built a new onedir AIRWorker and compared embedded bytecode/constants for all four modified runtime modules with current source; all matched. Verified bundled Chosun font (442,644 bytes).
- After checking both render workers were idle, gracefully stopped the manager, preserved the old bundle at `dist/render-audit-backup-20260921/AIRWorker`, installed the new bundle at the original path, and restarted it. Authenticated Local API check confirmed `render_worker` and `remote_drive_worker` idle and `local_api` running.
- The manager's Hermes role was already disabled because a separate Hermes process holds the singleton mutex; this unrelated state was not changed.

References: [FFmpeg perspective filter](https://ffmpeg.org/ffmpeg-filters.html#perspective), [ElevenLabs speech context and voice settings](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).

## Follow-up: all selectable web fonts

- The earlier audit did not verify every font. Added `auth-web/public/fonts/catalog.json` as the common source for the web selector and both ASS/image render paths.
- All 15 portable fonts now use local shared assets. Black Han Sans, Jua, Do Hyeon, and Nanum Myeongjo are downloaded from the official Google Fonts repository with their OFL license files. Nanum Myeongjo's previously mismatched CSS family spelling is corrected by the catalog.
- Converted NanumSquareExtraBold WOFF2 to SFNT at development time, avoiding a WOFF2 runtime dependency in AIRWorker.
- GmarketSans, Jalnan, and Binggrae Melona had a blank space glyph but no U+0020 cmap entry. The reproducible `tools/prepare_subtitle_font_assets.py` restores that mapping without modifying glyph outlines. Browser and worker both use the resulting assets.
- Each web face is explicitly registered at weight 700 (the preview's requested weight), preventing browser synthetic bold from changing the supplied outlines. Image rendering also uses the shared asset without substituting another bold file.
- New selections exclude Gungsuh and Malgun Gothic, which depend on Windows-installed fonts. Existing saved values are preserved and shown as Windows fonts. No Windows system font is redistributed as a web font.
- 53 relevant tests passed, including actual FFmpeg font-selection checks for all 15 fonts with Korean, Latin, digits and spaces. The compatibility image renderer also produced all 15 without fallback warnings.
- Production web deployment `dpl_71Zzy4bwbG3TAPR8ZtbMrkTeQjha` is Ready at `https://studio.airing.work`; all 15 served font files have SHA-256 hashes identical to the local worker source assets.
- Font-unified AIRWorker rebuilt; embedded code for five changed runtime modules matches current source and all 15 bundled source-font hashes match production. Replaced the idle worker after graceful shutdown, preserving the preceding bundle at `dist/font-parity-backup-20260921/AIRWorker`; confirmed render workers idle and Local API running after restart.

## Follow-up: preview sizing and sentence-safe narration (21:xx KST)

- Confirmed recovered v6 used 124px ASS font size at 1920px width for setting 6.5; the 440px web preview displayed 18.2px. Added a shared reference-canvas conversion (79.418px at 1920px), responsive cqw sizing in the web preview, matched padding/radius/stroke scale, and disabled ASS automatic wrapping of authored subtitle blocks.
- Actual 1920x1080 FFmpeg sample preserves “사고팔던 백 주인이었습니다. 그는” on one line. Headless Chromium measured preview boxes at widths 320/440/600: 199.125/273.891/373.406px, scaling proportionately.
- Old v6 TTS plan had five same-speaker API boundaries inside sentences, including “그 일을 달갑지 않게 여긴 사람이 / 있었습니다.” Added worker-side reconstruction (covers already queued legacy plans) and sentence-boundary grouping; all five are removed. Full spoken text remains identical and dialogue voice changes remain separate.
- Added subtitle character-span tracking so a subtitle containing parts of two sentences retains timing across synthesis segments. Timing remains an estimate based on character positions, not forced alignment; audio is not stretched to subtitle timing.
- Actual same-voice ElevenLabs scene16 test generated once: 16.904125 seconds, preserving selected speed 0.9, stability 0.62, similarity 0.82, style 0.18. No full project re-render. Subjective prosody still requires listening; do not claim every provider-internal pause is eliminated.
- Core tests: 37 passed plus additional timing regression passed (4 narration tests total). Broader checks: 25 passed, two unrelated failures (removed worker route and changed default worker profile); one legacy collection error references removed stdLocalMedia.ts. Did not revert concurrent migration work.
- Web build passed; production deployment dpl_Fmwhki6kznKBEHgeA8UGJW7b2BC2 Ready at studio.airing.work.
- Review samples: C:/Users/kimse/AppData/Local/AIRStudio/AIRWorker/output/subtitle-speech-check-20260921/corrected.png and narration-scene16.wav.
- Worker build completed successfully; embedded changed runtime modules match source and new narration_segments/subtitle_layout modules are bundled. Gracefully shut down idle worker, preserved bundle at dist/speech-layout-backup-20260921/AIRWorker, replaced dist/onedir/AIRWorker and restarted hidden. Verified render_worker and remote_drive_worker idle, local_api running; existing AIRWORKER_PROFILE=render_only honored.
- Confirmed production /std JS contains responsive cqw/container sizing. No full-project rerender was submitted automatically.
