; Inno Setup recipe: makes AuroraOS-Setup.exe (a normal Windows installer with Start-menu + desktop icons).
; Needs the PyInstaller output in dist\AuroraOS first.
#define AppName "Aurora OS"
#define AppVersion "1.0.0"
[Setup]
AppId={{6C3B1F52-AB0A-4D7E-9B2C-5A0B0A0A0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Aurora
DefaultDirName={autopf}\AuroraOS
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=AuroraOS-Setup
SetupIconFile=aurora.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\AuroraOS.exe
[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: checkedonce
[Files]
Source: "..\dist\AuroraOS\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\AuroraOS.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AuroraOS.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\AuroraOS.exe"; Description: "Open Aurora OS now"; Flags: nowait postinstall skipifsilent
; NOTE: shop data lives in %APPDATA%\AuroraOS and is never touched by installing, updating or uninstalling.
