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
