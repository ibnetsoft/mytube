# Project guidance

## Product and deployment target

- The active AIR Studio product is the web application in `auth-web/`, deployed to Vercel (project `mytube`). For web changes, update the web application, verify the relevant build, and deploy through the Vercel production workflow or its connected `main` branch.
- The Windows desktop/installer application is retired and is not a deployment target. Do not build, publish, update, or otherwise modify Windows packages or GitHub Releases for routine product work.
- Do not create or push `v*` Windows release tags, and do not run `tools/build_windows.ps1`, `tools/release_github.ps1`, or `.github/workflows/windows-release.yml`, unless the user explicitly asks to revive or release the Windows application.
- Before changing behavior, trace the active web execution path under `auth-web/`. A similarly named Python service under `services/` may belong to the retired desktop application and does not by itself implement the web feature.
