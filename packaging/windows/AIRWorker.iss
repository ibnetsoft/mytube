; [AIR-0227E-P2] AIR Worker installer - entirely separate from AIRStudio.iss:
; different AppId, different install root (Program Files, not
; %LOCALAPPDATA%), different Run registry key name, own version source
; (AIRWORKER_VERSION / worker/worker_version.py, not AIR_VERSION / version.py).
; Per this Task's explicit instruction, this must never share install path,
; registry keys, or update channel with the AIR Studio Desktop installer.
#define MyAppName "AIR Worker"
#define MyAppPublisher "AIR Studio"
#define MyAppExeName "AIRWorker.exe"
#define MyAppVersion GetEnv("AIRWORKER_VERSION")

[Setup]
AppId={{5E2A7B14-3C6D-4F91-B8E2-2A1D9C4F6E20}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; [P2-5] Binaries under Program Files (admin-owned, not user-writable) -
; separate from the mutable data directory (%LOCALAPPDATA%\AIRWorker,
; worker/worker_config.py's BASE_DIR default). This is the concrete
; reason AIRWorker needs admin privileges to install, unlike AIRStudio's
; per-user %LOCALAPPDATA% install.
DefaultDirName={autopf}\AIRWorker
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\..\release
OutputBaseFilename=AIRWorkerSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Onedir build output (packaging/windows/AIRWorker_onedir.spec via
; _dev/build_worker.py --onedir), not the onefile build - an installed,
; persistent binary directory is the natural fit for Inno Setup, and avoids
; onefile's variable self-extraction latency on every launch (P2-1/2
; finding). [P2 build isolation] dist/onedir/, not dist/ - keeps this
; separate from the onefile build's dist/onefile/AIRWorker.exe.
Source: "..\..\dist\onedir\AIRWorker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; [P2-9] Bundled third-party license notices, shipped alongside the binaries.
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; [P2-5] The one and only writable data root - matches worker_config.py's
; BASE_DIR default exactly (%LOCALAPPDATA%\AIRWorker). Nothing under {app}
; is ever written to at runtime.
Name: "{localappdata}\AIRWorker"
Name: "{localappdata}\AIRWorker\logs"
Name: "{localappdata}\AIRWorker\state"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start AIR Worker when Windows starts"; GroupDescription: "Startup:"; Flags: checkedonce

[Registry]
; Deliberately a distinct value name ("AIRWorker") in the same HKCU Run key
; AIRStudio.iss also uses - two independent entries, neither overwrites the
; other, and uninstalling one never touches the other's entry.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AIRWorker"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Data directory is left in place by default (support triage / reinstall
; convenience, same convention as AIRStudio.iss keeping current.json) -
; only logs are cleaned automatically. State (jobs.db, DPAPI token) is left
; for the operator to decide whether a reinstall should be a fresh start.
Type: filesandordirs; Name: "{localappdata}\AIRWorker\logs"
