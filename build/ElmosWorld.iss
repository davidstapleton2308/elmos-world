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
