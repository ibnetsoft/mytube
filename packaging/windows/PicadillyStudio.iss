#define MyAppName "Picadilly Studio"
#define MyAppPublisher "Picadilly Studio"
#define MyAppExeName "PicadillyLauncher.exe"
#define MyAppVersion GetEnv("PICADILLY_VERSION")

[Setup]
AppId={{8C1E61D9-9F2E-4C85-9D43-80E9F614E7B3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\PicadillyStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=PicadillyStudioSetup-{#MyAppVersion}
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
Source: "..\..\release\staging\PicadillyStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{userappdata}\PicadillyStudio"
Name: "{localappdata}\PicadillyStudio\logs"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Launcher\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start Picadilly Studio when Windows starts"; GroupDescription: "Startup and update:"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PicadillyStudio"; ValueData: """{app}\Launcher\{#MyAppExeName}"""; Tasks: startup

[Run]
Filename: "{app}\Launcher\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\PicadillyStudio\logs"
