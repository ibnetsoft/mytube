#define MyAppName "AIR Studio"
#define MyAppPublisher "AIR Studio"
#define MyAppExeName "AIRLauncher.exe"
#define MyAppVersion GetEnv("AIR_VERSION")

[Setup]
AppId={{8C1E61D9-9F2E-4C85-9D43-80E9F614E7B3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\AIRStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=AIRStudioSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\release\staging\AIRStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{userappdata}\AIRStudio"
Name: "{localappdata}\AIRStudio\logs"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start AIR Studio when Windows starts"; GroupDescription: "Startup and update:"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AIRStudio"; ValueData: """{app}\Launcher\{#MyAppExeName}"""; Tasks: startup

[Run]
Filename: "{app}\Launcher\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\AIRStudio\logs"
