; [AIR-0227E-P2-VALIDATION] AIR Worker installer - entirely separate from
; AIRStudio.iss: different AppId, different install root (Program Files,
; not %LOCALAPPDATA%), different Run registry key name, own version source
; (AIRWORKER_VERSION / worker/worker_version.py, not AIR_VERSION /
; version.py). Per this Task's explicit instruction, this must never share
; install path, registry keys, or update channel with the AIR Studio
; Desktop installer - the data DIRECTORY is a sibling under the same
; %LOCALAPPDATA%\AIRStudio\ vendor folder (confirmed decision), but that is
; a data-location choice only, not a channel merge.
#define MyAppName "AIR Worker"
#define MyAppPublisher "AIR Studio"
#define MyAppExeName "AIRWorker.exe"
#define MyAppVersion GetEnv("AIRWORKER_VERSION")

[Setup]
AppId={{5E2A7B14-3C6D-4F91-B8E2-2A1D9C4F6E20}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
; [P2-VALIDATION §9] Reuses the exact same Named Mutex name
; worker/single_instance.py creates (Global\AIRWorker_Manager_SingleInstance) -
; Inno Setup's built-in AppMutex support then automatically detects a
; running Manager and asks the user to close it before install/uninstall
; proceeds, instead of silently installing over (or deleting under) a live
; process.
AppMutex=Global\AIRWorker_Manager_SingleInstance
; [P2-VALIDATION §5] Binaries under Program Files (admin-owned, not
; user-writable) - separate from the mutable data directory
; (%LOCALAPPDATA%\AIRStudio\AIRWorker, worker/worker_config.py's BASE_DIR
; default). This is the concrete reason AIRWorker needs admin privileges to
; install, unlike AIRStudio's per-user %LOCALAPPDATA% install.
DefaultDirName={autopf}\AIRWorker
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\..\release
OutputBaseFilename=AIRWorkerSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

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
; This already includes AIRWorker.exe, _internal/ (all deps), ffprobe.exe
; (bundled via the spec's binaries=), and licenses/FFmpeg-LICENSE.txt +
; licenses/THIRD_PARTY_NOTICES.txt (bundled via the spec's datas=) - no
; separate Source: line needed for any of those, the wildcard covers them.
Source: "..\..\dist\onedir\AIRWorker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; [P2-VALIDATION §1] Canonical data root - matches worker_config.py's
; BASE_DIR default exactly (%LOCALAPPDATA%\AIRStudio\AIRWorker). Nothing
; under {app} is ever written to at runtime. Subpaths match
; worker_config.py's full canonical set (output/temp/config/crash/update/
; quarantine are reserved - see worker_config.py comments for which are
; actually wired to a consumer today).
Name: "{localappdata}\AIRStudio\AIRWorker"
Name: "{localappdata}\AIRStudio\AIRWorker\logs"
Name: "{localappdata}\AIRStudio\AIRWorker\state"
Name: "{localappdata}\AIRStudio\AIRWorker\ipc"
Name: "{localappdata}\AIRStudio\AIRWorker\temp"
Name: "{localappdata}\AIRStudio\AIRWorker\output"
Name: "{localappdata}\AIRStudio\AIRWorker\config"
Name: "{localappdata}\AIRStudio\AIRWorker\crash"
Name: "{localappdata}\AIRStudio\AIRWorker\update"
Name: "{localappdata}\AIRStudio\AIRWorker\quarantine"

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
; Logs are always cleaned automatically. State/output (jobs.db, DPAPI
; token, delivered renders) are handled by the interactive prompt in
; [Code] below instead - a silent/unattended uninstall (common in CI or
; scripted ops) must not destroy render output or job history by default.
Type: filesandordirs; Name: "{localappdata}\AIRStudio\AIRWorker\logs"

[Code]
const
  RegUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';

function GetInstalledVersion(): String;
begin
  if not RegQueryStringValue(HKLM, RegUninstallKey, 'DisplayVersion', Result) then
    if not RegQueryStringValue(HKCU, RegUninstallKey, 'DisplayVersion', Result) then
      Result := '';
end;

// [P2-VALIDATION §6] Downgrade warning/block - Inno Setup has no built-in
// semver comparison, so this does a straightforward string/component
// comparison good enough for our own major.minor.patch scheme
// (worker/worker_version.py). A malformed or unparsable installed version
// string is treated as "unknown, allow install" rather than blocking.
function CompareVersion(V1, V2: String): Integer;
var
  P1, P2: Integer;
  N1, N2: Integer;
  S1, S2: String;
begin
  Result := 0;
  S1 := V1 + '.';
  S2 := V2 + '.';
  while (Length(S1) > 0) and (Length(S2) > 0) and (Result = 0) do
  begin
    P1 := Pos('.', S1);
    P2 := Pos('.', S2);
    if (P1 = 0) or (P2 = 0) then
      break;
    N1 := StrToIntDef(Copy(S1, 1, P1 - 1), 0);
    N2 := StrToIntDef(Copy(S2, 1, P2 - 1), 0);
    if N1 <> N2 then
      Result := N1 - N2;
    S1 := Copy(S1, P1 + 1, Length(S1));
    S2 := Copy(S2, P2 + 1, Length(S2));
  end;
end;

function InitializeSetup(): Boolean;
var
  InstalledVersion: String;
  Cmp: Integer;
begin
  Result := True;
  InstalledVersion := GetInstalledVersion();
  if InstalledVersion <> '' then
  begin
    Cmp := CompareVersion('{#MyAppVersion}', InstalledVersion);
    if Cmp < 0 then
    begin
      MsgBox('설치된 AIR Worker 버전(' + InstalledVersion + ')이 이 설치 파일의 버전(' +
             '{#MyAppVersion}' + ')보다 최신입니다. 하위 버전으로의 설치는 지원되지 않습니다.' + #13#10 +
             '먼저 기존 버전을 제거한 후 다시 시도하세요.',
             mbError, MB_OK);
      Result := False;
    end
    else if Cmp = 0 then
    begin
      if MsgBox('AIR Worker ' + InstalledVersion + '이(가) 이미 설치되어 있습니다.' + #13#10 +
                '동일 버전을 재설치하시겠습니까?', mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
    end;
    // Cmp > 0 (정상 업그레이드)는 그대로 진행 - Inno Setup 기본 동작.
  end;
end;

// [P2-VALIDATION §6/§9] Uninstall-time user-data retention choice - a
// silent uninstall never deletes user data (only [UninstallDelete]'s logs
// cleanup runs); an interactive uninstall asks explicitly.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if not UninstallSilent() then
    begin
      DataDir := ExpandConstant('{localappdata}\AIRStudio\AIRWorker');
      if DirExists(DataDir) then
      begin
        if MsgBox('사용자 데이터(설정, 작업 기록, 렌더 결과물 등)를 완전히 삭제하시겠습니까?' + #13#10 +
                  '위치: ' + DataDir + #13#10 +
                  '"아니오"를 선택하면 재설치 시 이어서 사용할 수 있도록 보존됩니다.',
                  mbConfirmation, MB_YESNO) = IDYES then
          DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
