> 2026-10-27: 별도 보관된 비활성 옵션입니다. 현재 제작은 After Effects와 기본 FFmpeg 조립을 사용합니다. 아래는 과거 통합·설치 기록이며 활성 운영 지침이 아닙니다. [현행 역할 계약](worker-workflow-boundary.md)을 따릅니다.

# Motion Studio · EffectCraft engine

EffectCraft is an additional, explicitly selected production engine. Existing Adobe AE and browser Motion Studio paths remain available; existing projects still default to AE. Each choice preserves its own settings in `motion.alternatives`.

## Build and installation

Upstream: https://github.com/storytold/effectcraft

The exact source revision/version/license is recorded in `auth-web/lib/effectcraftSource.json`. Source checkout, Rust toolchain and build cache are local, under ignored `.codex-temp/`; binaries are not committed or bundled into the Vercel application.

Install Rust >=1.95 from https://rustup.rs and the normal host compiler prerequisites, then run:

```sh
python scripts/build_effectcraft.py --jobs 2
```

This builds unmodified upstream `effectcraft` and `effectcraft-cli` in release mode using `Cargo.lock`. It does not run tests, open the application, render a demo, or produce a customer video. Binaries, hashes, source revision and upstream notices/licenses are packaged at:

```text
output/effectcraft/<platform>-<architecture>/
  effectcraft-cli[.exe]
  effectcraft[.exe]
  build-manifest.json
  LICENSE-MIT / LICENSE-APACHE / NOTICE / ATTRIBUTION.md
  assets/... and docs/brand/... license and attribution sidecars
```

The worker discovers the matching host directory automatically. Alternatively set `EFFECTCRAFT_CLI` to the packaged CLI's absolute path; its sibling `build-manifest.json` is required. Runtime validates the pinned source revision and CLI SHA-256 before executing it. A Mac binary does not install or update the office Windows worker: build/package for that host separately when office work resumes. Do not run AIR Studio's retired Windows installer/release scripts.

## Active web and worker path

1. In Motion Studio's production selector choose **Motion Studio · EffectCraft**, save the production mode and submit the finalized project normally. The checkbox/radio for short AI inserts remains separate; `ae_only` retains its existing stored meaning of no video-generation API even under EffectCraft.
2. The existing submission validator still requires finalized narration identity, timing, completed pre-submission preparation and reviewed PSD layer packages. Script/preparation worker and submitted production-worker ownership boundaries are unchanged.
3. `stdMotionAutomation.ts` seals `renderer.engine=effectcraft` and the pinned revision into the same immutable submission envelope. The service-only `register_std_effectcraft_pipeline` RPC commits it as the distinct `effectcraft_automation` queue kind in one transaction, preventing older AE workers from claiming it. The migration retains existing AE registration and extends the same lease/completion guards; EffectCraft completion additionally requires review evidence for the frozen renderer. Provider secrets remain in the existing encrypted store.
4. The retained motion automation worker runs with `--engine effectcraft` for this queue and dispatches only such frozen scenes to `worker/effectcraft_render.py`. It localizes the reviewed layers or source media, emits a bounded script using our existing public-API scene emitter, creates an editable `.ecproj` through the CLI, and renders the visual clip using EffectCraft.
5. Final voice, captions, saved templates, BGM/SFX, optional short AI inserts and actual-output review use the existing production pipeline. Render success alone never approves a scene. Reviewed outputs follow the existing atomic completion/admin-review flow; no automatic publishing or YouTube upload is added.

The EffectCraft child process has isolated preferences per render directory and does not receive the worker's provider credentials. Create/render JSON receipts, logs, script, editable project and output hashes are preserved. Missing binary, source-version mismatch, absent required properties/effects, or engine failure causes `needs_review`; no silent AE fallback or effect removal is permitted.

## Initial scope and deferred validation

- Connected adapters: existing stills/videos; pre-reviewed separated PSD layers; saved camera/layer transforms, parallax, prepared bend/light/effect plans via EffectCraft's AE-style scripting API; exact scene duration/aspect and subsequent existing audio/caption composition.
- This does not import `.aep`, load Adobe plug-ins, or establish that similarly named EffectCraft effects produce the same pixels. The engine's public property/effect compatibility still needs actual rendering verification.
- Browser-only financial scenes, dialogue-direction cues, native vector/effect scenes, and advanced mesh/skeletal/skin settings are rejected before submission rather than silently dropped. Use their existing browser path or prepare a supported AE/PSD package. Arbitrary conversion of those structures is not implemented here.
- A source video shorter than its finalized scene is rejected; missing frames are not invented.
- Per the user's instruction, no functional, render, visual parity, paid video-generation, or office-worker tests are run in this integration task. Compilation/build status must be reported separately. Do not label an installed engine, a successful build, or this adapter as verified production quality.

EffectCraft is unmodified upstream code under MIT OR Apache-2.0. Preserve the copied notices and asset/font licenses with distributed binaries. ArtCraft trademarks retain their upstream restrictions; AIR Studio does not rebrand the upstream executable. Source links and pin identify which upstream build is being used.

## Recorded build status · 2026-10-20

- Native release build completed on this Mac (`Darwin`, `arm64`, Rust 1.99.1), both desktop and CLI binaries. Packaged directory: `output/effectcraft/darwin-arm64/`; receipt: `build-manifest.json`.
- CLI SHA-256: `56ec591ce3e291bd97da99fa9a7857beb6281c5e298bc30746b60c4be9470eb9`.
- Desktop SHA-256: `93e0b368d6509097aeca1bb05b9fbef05614f2a0ffe39dacfad2f8428c89041d`.
- Next.js production compilation, TypeScript compilation, Python bytecode compilation and native worker UI bundling completed. The dedicated queue migration was applied; deployed function grants are service-only. These are build/deployment checks, not functional acceptance.
- Neither EffectCraft binary was launched. No demo/customer render, automated test suite, AE parity comparison, paid generation, or office Windows installation was performed. The office worker still needs its host-specific engine build and code update when that deferred work resumes.

## Office Windows follow-up · 2026-10-20

- Updated the office checkout to `41e2c359` with `git pull --ff-only`, preserving existing staged, unstaged and untracked work.
- Installed Rust 1.99.1 locally under `.codex-temp/` and Visual Studio Build Tools 2022 (MSVC 14.44, Windows SDK 10.0.26100). The release build used the x64 environment from `Common7/Tools/VsDevCmd.bat` and `python scripts/build_effectcraft.py --jobs 2`.
- Both unmodified upstream binaries built successfully; licenses and manifest are in `output/effectcraft/windows-amd64/`. CLI SHA-256: `9953695ce537debc5f9b3c8c90d5af62ea82e7f71e3716f0facfe68029d4cd62`; desktop SHA-256: `8819f684c60eff6fec49a8ca67150b47759cbe0db20093db946a79fe263bf6f1`.
- A real worker-adapter smoke render exposed the script file-read gate for unsaved projects. The adapter now saves an empty project before importing its local media; the original isolated preferences and credential filtering remain in effect.
- With that repair, the worker adapter created an editable project and a 1920×1080, 24 fps, one-second H.264 MP4 from a synthetic image with camera zoom. Full FFmpeg decoding passed and the first frame was visually inspected. Evidence is in `output/effectcraft/windows-smoke-20261020/` (script, project, command receipts, video and frame).
- This verifies one local image/camera rendering path. It does not verify customer jobs, PSD/effect parity, audio/caption composition, GPU rendering or administrator publishing. The build manifest retains its build-time `render_validation: not_run`; the later smoke evidence is separate.
- Restarted the existing local media supervisor gracefully (new PID `39456`). A pre-existing database timeout cleared; the final loopback health response reported `idle`, no active job, no pending roles and no queue error at 23:27 KST. Existing AE remains installed and available.

## PSD colour / small-blur follow-up · 2026-10-21

The archived project 3376 scene 25 PSD was rendered with its original layer/camera keys and compared to its 10-second AE reference. The reference AEP uses Rec.709 Gamma 2.4 and 16 bpc; the original unmanaged 8-bpc EffectCraft project caused the main brightness mismatch. `worker/effectcraft_compatibility.py` now explicitly applies the measured Rec.709 working/output configuration through public native commands; the production adapter records the compatibility receipt before rendering.

For affected static opaque stills, a normalized native convolution preserves fractional Gaussian coefficients that upstream's integer-box approximation discards. Other affected transparency/mask/animation cases are rejected for review. Upstream binaries remain unmodified. Original scene amount 0.35 is preserved and still below RGB output precision; 0.7 and 1.0 now produce nonzero pixel changes where the old renderer produced none. This is not a strength boost or a claim of exact Adobe subpixel-kernel parity.

Eight paired output samples improved mean RGB MAE from 8.39 to 1.94/255; the 1-second lossless comparison is 0.55/255. Both outputs decode to 240 frames at 1920×1080/24 fps. Layer order and transform keys are unchanged. Twelve focused regression tests and the production adapter's smoke render passed. Evidence and limitations: `output/effectcraft/psd-3376-scene25-fix-20261021/REPORT.md`. This validates the archived PSD scene and the local compatibility path, not a new customer submission or full prepared-package queue flow.

## Scene 29 vignette follow-up · 2026-10-21

The richer scene-29 experiment exposed two inverted-feather-mask differences: coverage was clipped to the solid before blurring/inversion, and native smooth-feather units differed from AE. The local compatibility adapter now pads generated static vignette solids while translating anchor/path together, and converts feather units by 0.75, independently measured with three AE half-plane controls. Opacity envelopes, world geometry, artwork, motion and other effects are preserved; unsupported mask rigs require review. Native binaries remain unmodified.

The same 10-second/240-frame scene was rerendered against its preserved exact AE reference. Isolated effect-difference MAE improved 4.312→0.692/255 and eight-sample full-scene mean MAE 3.398→2.225/255. Pure-mask MAE is 0.634/255. Nineteen focused regression tests passed; AE calibration/render wrappers and final window checks required no user popup handling. Evidence, reproduction and scope: `output/effectcraft/psd-3376-scene29-vignette-fix-20261021/REPORT.md`. Residual raster/color differences remain; this is a local archived-scene comparison, not blanket AE equivalence or queue acceptance.

## Scene 29 residual follow-up · 2026-10-21

Further controls isolated an excessively strong native integer-box Gaussian at static amount 1.2, the light-sweep mask's feather-unit discrepancy, untagged color-matrix metadata in the preserved AE comparison MP4, and first-keyframe loss in the native default 15 Mbps intermediate. The helper now uses an independently measured normalized response with local gamma decode/encode for the supported static 1.2 Both-dimensions opaque-still case, extends the verified mask-domain/unit conversion to the generated light sweep, and explicitly exports native H.264 intermediates at 40 Mbps. Source settings and upstream binaries are preserved. Unsupported calibrated cases require review. AE reference metadata is corrected only in a comparison copy, without sample re-encoding.

Using the same correctly interpreted AE reference on both sides of the before/after measurement, nine-sample lossless mean MAE improved 1.202→0.549/255 and encoded-video mean MAE 1.756→1.017/255. Independent colored step/checker error improved 22.852→0.686/255 through the actual helper. AE's own repeated baseline differed by 0.542/255; residual native differences are similar in scale, not a claim of identical pixels. Both final outputs are 240 frames; full decoding, layer/motion preservation audit and 33 focused tests passed. Old EffectCraft reviewed visual caches are now invalidated by compatibility version; AE caches are unchanged. No jobs were enqueued. Evidence and limitations: `output/effectcraft/psd-3376-scene29-residual-fix-20261021/REPORT.md`.

## Scene 25 cross-scene regression · 2026-10-21

The current v3 helper/export was applied to the archived scene 25 with its original 0.35 blur and sustained motion. Nine lossless original-scene samples are pixel-identical to the prior corrected native output; color settings and all authored artwork/motion properties are preserved. Weak-blur 0.35/0.7/1.0 controls likewise exactly match their archived corrected PNGs. A separate four-effect experiment improves mean lossless AE difference 2.771→0.800/255; isolated light/vignette improve while particles/ring remain pixel-identical before/after, with all eight particles detected. A separate 1.2 blur probe improves 1.265→0.551/255 across three times on the new artwork. Scene 29 controls remain pixel-identical at three times. Both original/experimental videos decode to 240 frames; 33 relevant tests passed, and no AE popup was left for the user.

No new regression was found in these controls. Existing scene-25 motion/sampling differences at 0.5/7 s remain exactly unchanged, so the original nine-sample lossless MAE 0.802 is not entirely dithering. Original scene effects were not augmented; extra effects and amount 1.2 exist only in explicitly separate diagnostic copies. Evidence, videos, independent controls and scope: `output/effectcraft/psd-3376-scene25-v3-regression-20261021/REPORT.md`.

## Scene 25 spatial-motion correction · 2026-10-21

The previously recorded motion difference is now traced to spatial-key defaults: the inspected AE references store straight zero-handle Position paths with spatial auto-Bezier off, while native key creation enables automatic neighbour handles. This curved scene25's intermediate paths and caused motion during its identical-endpoint 4–10 s hold. v4 adds an explicit linear-position declaration for the production scene emitter/verified importers and converts only eligible implicit-auto multi-key paths through public commands. Arbitrary authored auto curves are not inferred from zero stored handles or flattened; ambiguous cases require review. Original key times/values, temporal interpolation, artwork, blur, color and effects are preserved. Old EffectCraft reviewed visual caches invalidate via the existing compatibility-version check.

All 240 frame transforms were compared against actual AE values. Maximum coordinate error reduced from 2.880 to 0.0161 pixels; the native hold is now exactly stationary. Twenty dense lossless samples improve mean MAE 1.661→0.548/255, with no corrected sample over 0.552. The full 10-second scene was rerendered, and its separate effect-copy controls also improve. Scene29's independently rerendered full MP4 is SHA-256 identical to its preceding output, including all 240 decoded frame hashes. Thirty-nine relevant tests and an actual production-adapter smoke passed; no AE popup was left for the user. Evidence and limitations: `output/effectcraft/psd-3376-scene25-motion-fix-20261021/REPORT.md`.

## Remaining PSD scene coverage · 2026-10-21

A fresh read-only inventory of project3376 found 100 scenes and 608 assets, with PSD associations only for scenes19/25/29. The remaining scene19 was rendered with v4 in its latest 3-second one-way version and two archived 7-second one-way/sustained versions. All 408 frame transforms match AE within 0.017px; 41 newly rendered AE lossless controls have per-version mean MAE 0.5422/0.5405/0.5386 per255. Original PSD/AEP hashes and authored layer/transform/mask/effect parameters are preserved, and both complete videos in each pair decode successfully. Original blur amounts are 0.3/0.3/0.35; the original scene19 has no extra vignette/light/particle/ring effects. Those effects retain the existing scene25/29 control evidence; they were not newly added or rerendered here. No production engine changes were necessary, 39 focused tests passed, and AE completed without leaving a user-operated popup. Evidence: `output/effectcraft/psd-3376-remaining-20261021/REPORT.md`.

## Applied project3376 and complete composition · 2026-10-21

Reviewed native clips19/25/29 are now assigned in the real web project. The actually selected scene29 sustained direction was additionally validated against its original AE project (lossless MAE0.5400/255; max position difference0.0161px) before application. Native playback speed is preserved and the last frame is held through the recorded narration interval. The full composition uses these three EffectCraft clips, the existing reviewed AE scene23, and96 current original images; nine stale videos fail current visual identity and remain preserved outside the render. Final recording text/timing remain unchanged; recorded voice IDs and the existing footsteps storage reference were repaired without generating new narration.

The active web queue/local-worker path exposed repeated static-image composition. `MotionFrames` now reuses a completed static frame only with constant keys, no effects, a cut transition and no caption overlays; animated/video/transition paths remain intact. Forty-three relevant tests passed. The complete1080p/24fps render is26m54.42s. Actual review covered498 samples across all100 scenes/99 cuts,96 original-image midpoint comparisons and18 native-vs-final controls. Static cut timing is within one24fps frame; compression residuals remain. Low-contrast white captions were repaired with a2px outward black outline; the whole pre-caption MP4 remains SHA256-identical across that repair. Final v3 queue `7b780cfa-7bca-4596-81c0-4372d23a78fb` is completed/reviewed; local/GCS manifest SHA256 agrees (`76cb3a722a5805c48e6b7dbe20b571eaacbfb6b8c8b4f699cc23030a2b8d3791`). No AE popup remains, supervisor is idle/unpaused, and administrator publication was not performed. Evidence and scope: `output/effectcraft/project-3376-final-20261021/REPORT.md`.
