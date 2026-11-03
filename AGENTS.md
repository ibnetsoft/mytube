# Project guidance

## Product and deployment target

- The active AIR Studio product is the web application in `auth-web/`, deployed to Vercel (project `mytube`). For web changes, update the web application, verify the relevant build, and deploy through the Vercel production workflow or its connected `main` branch.
- The Windows desktop/installer application is retired and is not a deployment target. Do not build, publish, update, or otherwise modify Windows packages or GitHub Releases for routine product work.
- Do not create or push `v*` Windows release tags, and do not run `tools/build_windows.ps1`, `tools/release_github.ps1`, or `.github/workflows/windows-release.yml`, unless the user explicitly asks to revive or release the Windows application.
- Before changing behavior, trace the active web execution path under `auth-web/`. A similarly named Python service under `services/` may belong to the retired desktop application and does not by itself implement the web feature.

## Subtitle review translation

- Subtitle review translations (including the `KO` text beside Japanese subtitles) must run through the local Codex CLI script worker on this computer. Do not call Gemini or OpenAI model APIs for these translations.
- The web app queues translation requests in the database and reads their results. The local script worker claims requests and publishes validated translations. Preserve existing translations for unchanged subtitle text.
- Normalize punctuation-only subtitle fragments after quote and AI dialogue splitting, and when reopening saved subtitles. Fixing initial text-length splitting alone is insufficient. Preserve the preceding speaker and recorded narration timing when attaching punctuation.

## Codex-supervised submission automation

- The user explicitly authorized Codex to perform AE direction approval and output review on 2026-10-06. This supersedes user-click approval requirements above for the supervised submission flow. Codex must inspect actual source imagery, finalized narration, scene directions, and rendered output before approving; uncertainty must trigger repair or escalation, never blind approval.
- The local thread heartbeat monitors submitted AE jobs every 15 minutes, preserves reusable audio and source assets, repairs recoverable interruptions, and continues through final render. Administrator publishing and YouTube uploads remain separate.
- Use `node scripts/std_continue_submission.cjs PROJECT_ID` to inspect current jobs. After evidence-based approval, `--enqueue` validates current fingerprints and reviewed assets, records the render queue ID, and avoids registering the same reviewed job again. Confirm render completion separately.

## Complete production and record quality findings

- On 2026-10-28 the user requested that quality concerns never block production. Continue through final assembly with the existing source and saved direction; keep actual failed or uncertain review results truthful and record them separately as quality notes. This supersedes the earlier quality-approval stopping rule for submitted media production.
- Preserve cancellation, ownership, source integrity and actual file/timing checks. Execution failures remain queued for automatic recovery with backoff and reusable assets preserved; never mark an absent or broken output complete.
- Final delivery must include the quality-notes report and retain administrator publishing/YouTube upload as separate actions.

## Camera preference

- On 2026-10-29 the user required different facial identities across topics and among different characters within a topic. Compare actual stored reference imagery across all categories; hair, clothes, expression and wrinkles alone do not establish distinctness. Redesign similar new faces and preserve existing topic assets. Keep each character's approved identity consistent within its own topic.

- On 2026-10-29 the user prohibited slow zooms. Never add slow or whole-scene gentle zooms. Prefer a fixed camera; when motivated, use a clearly visible medium-speed zoom with a short movement window and holds. Preserve uploaded footage; this rule governs added direction, not source footage already containing camera movement.

## Confirm settings before new scripts

- Before starting a new script, ask the user to choose or confirm the production/script type, subject/category/reference, duration/chapter length, language/country/era, image/direction style, parallax/layer/video-scene scope, scene-state changes, and music-prompt/additional requests. Show the final effective settings and wait for an explicit start action. Saved defaults alone are not confirmation.
- Apply this to new script creation, including agent-initiated creation. Continue already running or recovering jobs with their existing settings; do not interrupt them to repeat the questions.

## Current-affairs production defaults

- For current-affairs or economic documentary productions, read `docs/current-affairs-production-defaults.md` and apply its defaults to the proposed settings and production. Confirm the effective settings and receive an explicit start action for each new script as required above; defaults do not replace confirmation. User overrides take precedence.
- For authorized supervised production, continue through final assembly without waiting for user review or approval; inspect evidence, preserve truthful quality notes and recover execution failures as described above. Do not automatically publish or upload.

## Wuxia webtoon production defaults

- For 무협 웹툰 productions, read `docs/wuxia-webtoon-production-defaults.md` and apply the defaults to the proposed settings and production. Confirm the effective settings and receive an explicit start action for each new script as required above; user overrides take precedence.
