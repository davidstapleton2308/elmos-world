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
