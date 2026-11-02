; Inno Setup script for the Nuitka standalone build.
; Compile with: iscc build\installer.iss   (after build\build.ps1)

#define AppName "THERMAL//DOTS"
#define AppVersion "1.0.0"
#define AppExe "tdots.exe"

[Setup]
AppId={{8E1B2E44-6C1F-4E4F-9E42-1C7E5B2A9D01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=thermal-dots
DefaultDirName={autopf}\ThermalDots
DefaultGroupName={#AppName}
OutputDir=..\build\installer
OutputBaseFilename=thermaldots-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\build\nuitka\tdots.dist\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "gui"
Name: "{group}\{#AppName} (CLI)"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "gui"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "gui"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
{ WebView2 is required by the GUI. The CLI works without it, so this is a
  warning rather than a hard block. }
function InitializeSetup(): Boolean;
var
  Version: String;
begin
  Result := True;
  if not RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
     and not RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
  begin
    if MsgBox('Microsoft Edge WebView2 is not installed.' + #13#10 +
              'The CLI will work, but the GUI needs it.' + #13#10#13#10 +
              'Continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;
