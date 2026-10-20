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
