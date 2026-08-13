# Windows packaging

This folder contains the Windows distribution setup. The installer and portable ZIP both package the desktop application directly; no update launcher or release manifest is included.

## Package layout

```text
AIRStudio/
  AIRStudio.exe
  _internal/
```

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

1. Install Inno Setup and run the build without `-SkipInstaller`.
2. Upload the generated ZIP and installer to the intended release channel.
3. Keep the optional startup setting enabled when AIR Studio should launch on Windows login.
