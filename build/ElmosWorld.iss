#define MyAppName "Elmos World"
#define MyAppVersion "3.1.1"
#define MyAppExeName "ElmosWorld.exe"

[Setup]
AppId={{3E87116F-2395-4932-9543-711795ECB357}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName=Elmos World {#MyAppVersion}
AppPublisher=Elmos World
VersionInfoVersion=3.1.1.0
DefaultDirName={localappdata}\Programs\Elmos World
DefaultGroupName=Elmos World
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist_setup
OutputBaseFilename=ElmosWorld_Setup_3.1.1
SetupIconFile=..\app\elmos_world.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
AppMutex=Local\ElmosWorldDesktopApp
ChangesAssociations=no
DisableDirPage=yes
DisableWelcomePage=no
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "preinstall_backup.ps1"; Flags: dontcopy
Source: "restore_previous.ps1"; Flags: dontcopy
Source: "..\dist\ElmosWorld\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Elmos World"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\Elmos World"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Elmos World"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Params: String;
begin
  Result := '';
  if not FileExists(ExpandConstant('{app}\\ElmosWorld.exe')) then Exit;
  ExtractTemporaryFile('preinstall_backup.ps1');
  ExtractTemporaryFile('restore_previous.ps1');
  Params := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{tmp}\\preinstall_backup.ps1') + '" -AppDir "' + ExpandConstant('{app}') + '"';
  if not Exec(ExpandConstant('{sys}\\WindowsPowerShell\\v1.0\\powershell.exe'), Params,
     '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    Result := 'The existing Elmos World could not be backed up. No update files have been installed. Please close Elmos World and try again.';
end;

function ControllerHelperPath: String;
begin
  Result := ExpandConstant('{app}\\_internal\\controller-runtime\\ElmosControllerRuntime.exe');
end;

function ControllerBridgePath: String;
begin
  Result := ExpandConstant('{app}\\_internal\\controller-lab\\bridge\\publish\\Elmos.ControllerLab.Bridge.exe');
end;

function ControllerPrerequisiteLogPath: String;
begin
  Result := ExpandConstant('{localappdata}\\ElmosWorld\\logs\\installer-prerequisites.log');
end;

procedure LogControllerPrerequisite(const MessageText: String);
var
  LogPath: String;
begin
  LogPath := ControllerPrerequisiteLogPath;
  ForceDirectories(ExtractFileDir(LogPath));
  SaveStringToFile(LogPath,
    GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + ' ' + MessageText + #13#10, True);
end;

function CheckControllerPrerequisites(var ResultCode: Integer): Boolean;
var
  Params: String;
begin
  Params := '--bridge "' + ControllerBridgePath + '" check-prerequisites';
  Result := Exec(ControllerHelperPath, Params, ExpandConstant('{app}'),
    SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InstallControllerDriverElevated(var ResultCode: Integer): Boolean;
var
  Params: String;
begin
  Params := '--bridge "' + ControllerBridgePath + '" install-driver';
  // Only this driver helper is elevated. The Elmos application remains a
  // per-user install and downloaded games are never launched as administrator.
  Result := ShellExec('runas', ControllerHelperPath, Params,
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Started: Boolean;
begin
  if CurStep <> ssPostInstall then
    Exit;

  LogControllerPrerequisite('Starting post-install controller prerequisite audit.');
  if not FileExists(ControllerHelperPath) then
  begin
    LogControllerPrerequisite('Controller helper missing: ' + ControllerHelperPath);
    MsgBox('Elmos World was installed, but its controller helper is missing. Controller translation will remain unavailable until Elmos World is repaired or updated.',
      mbError, MB_OK);
    Exit;
  end;
  if not FileExists(ControllerBridgePath) then
  begin
    LogControllerPrerequisite('Controller bridge missing: ' + ControllerBridgePath);
    MsgBox('Elmos World was installed, but its virtual-controller bridge is missing. Controller translation will remain unavailable until Elmos World is repaired or updated.',
      mbError, MB_OK);
    Exit;
  end;

  Started := CheckControllerPrerequisites(ResultCode);
  if Started and (ResultCode = 0) then
  begin
    LogControllerPrerequisite('Controller driver and preparation are ready; no driver installation needed.');
    Exit;
  end;

  if not Started then
  begin
    LogControllerPrerequisite('Read-only prerequisite check could not start. Exec returned false.');
    MsgBox('Elmos World was installed, but Windows could not run its controller readiness check. The rest of the application is installed. You can retry controller setup from Settings.',
      mbInformation, MB_OK);
    Exit;
  end;

  LogControllerPrerequisite('Read-only prerequisite check exit code: ' + IntToStr(ResultCode));
  if (ResultCode <> 10) and (ResultCode <> 11) and (ResultCode <> 12) then
  begin
    MsgBox('Elmos World was installed, but the controller driver status could not be verified (check code ' +
      IntToStr(ResultCode) + '). The rest of the application is installed. You can retry from Settings.',
      mbInformation, MB_OK);
    Exit;
  end;

  if MsgBox('Elmos World is installed, but its virtual-controller driver is missing or needs repair.' + #13#10 + #13#10 +
      'This driver is required for Elmos to translate your physical controller into a virtual Xbox controller for games that require XInput.' + #13#10 + #13#10 +
      'Install or repair the driver now? Windows will show a separate administrator approval prompt. You can choose No and install it later from Elmos World Settings.',
      mbConfirmation, MB_YESNO) <> IDYES then
  begin
    LogControllerPrerequisite('User deferred virtual-controller driver installation.');
    Exit;
  end;

  LogControllerPrerequisite('User approved driver setup; requesting elevation for the controller helper.');
  Started := InstallControllerDriverElevated(ResultCode);
  if not Started then
  begin
    LogControllerPrerequisite('Elevated driver helper could not start or UAC was cancelled.');
    MsgBox('Elmos World is installed, but Windows did not allow the controller driver setup to start. No Windows security settings were changed. You can retry from Settings.',
      mbInformation, MB_OK);
    Exit;
  end;

  Started := CheckControllerPrerequisites(ResultCode);
  if Started and (ResultCode = 0) then
  begin
    LogControllerPrerequisite('Driver installation completed and readiness was verified.');
    MsgBox('Controller setup completed. Elmos World verified that the virtual-controller driver is installed and prepared.',
      mbInformation, MB_OK);
  end
  else
  begin
    LogControllerPrerequisite('Driver setup returned, but the readiness recheck failed with code ' + IntToStr(ResultCode));
    MsgBox('Elmos World is installed, but controller setup could not be verified. The application will still work; controller translation may remain unavailable. Check the installer prerequisite log in %LOCALAPPDATA%\\ElmosWorld\\logs.',
      mbInformation, MB_OK);
  end;
end;
