# Windows packaging

This folder contains the Windows distribution setup.

## Why GitHub Releases

GitHub Releases is a good free update host for this app. GitHub's release docs say a single release can have up to 1000 assets, each asset must be under 2 GiB, and there is no total release size or bandwidth limit.

## Package layout

The installed app is split into a stable launcher and replaceable app payload:

```text
PicadillyStudio/
  Launcher/
    PicadillyLauncher.exe
    PicadillyUpdater.exe
    update_config.json
  app/
    PicadillyStudio.exe
    _internal/
  current.json
```

`PicadillyLauncher.exe` checks the update manifest, downloads a newer zip when available, verifies SHA256, starts `PicadillyUpdater.exe`, and otherwise launches `app/PicadillyStudio.exe`.

`PicadillyUpdater.exe` replaces only the `app/` payload. Launcher updates can be delivered later by running the installer again.

The installer can also register `Launcher/PicadillyLauncher.exe` in the current user's Windows startup list. That means every Windows login opens the launcher first, the launcher checks `latest.json`, applies a newer app payload when available, and then starts the local app.

## Commands

From the repo root:

```powershell
.\tools\build_windows.ps1 -Version 0.1.0
```

To skip the Inno Setup installer and only create the portable zip:

```powershell
.\tools\build_windows.ps1 -Version 0.1.0 -SkipInstaller
```

## Release checklist

Before publishing a production installer:

1. Replace `OWNER/REPO` in `tools/build_windows.ps1` and `latest.example.json`.
2. Upload the generated zip and `latest.json` to GitHub Releases.
3. Install Inno Setup and run the build without `-SkipInstaller`.
4. Keep the startup option enabled in the installer when workers should stay current automatically on Windows login.
5. Re-run the installer when the launcher/updater binaries themselves need to change; normal app payload updates are handled through `latest.json`.
