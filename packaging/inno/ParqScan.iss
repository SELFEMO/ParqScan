; ParqScan Windows installer (Inno Setup)
; Build with: ISCC.exe /DAppVersion=0.3.0 packaging\inno\ParqScan.iss

#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif

#define AppName "ParqScan"
#define AppPublisher "ParqScan contributors"
#define AppExeName "ParqScan.exe"
#define BuildDir "..\..\dist\ParqScan"

[Setup]
AppId={{A3F9C2E1-8B4D-4F6A-9C1E-2D5A7B8C9E0F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\..\dist\installer
OutputBaseFilename=ParqScan-Windows-Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\..\parqscan\resources\ParqScan.ico
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
