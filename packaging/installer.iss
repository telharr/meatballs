; PZ Server Control Panel — zero-click local installer (v3.18)
; Build: 1) python packaging/build_exe.py  2) ISCC packaging/installer.iss

#define MyAppName "PZ Control Panel"
#define MyAppVersion "3.22.0"
#define MyAppPublisher "MEATBALLS"
#define MyAppURL "https://github.com/telharr/meatballs"
#define MyBuildDir "..\dist\PZControlPanel"
#define MyOutputDir "Output"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\PZControlPanel
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#MyOutputDir}
OutputBaseFilename=PZControlPanel-{#MyAppVersion}-setup
SetupIconFile=..\panel\static\assets\icon.ico
UninstallDisplayIcon={app}\PZControlPanel.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Запускать панель при входе в Windows"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "templates\env.local.template"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist
Source: "start_panel.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\start_panel.bat"; WorkingDir: "{app}"; IconFilename: "{app}\panel\static\assets\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\start_panel.bat"; WorkingDir: "{app}"; IconFilename: "{app}\panel\static\assets\icon.ico"

[Run]
Filename: "{app}\start_panel.bat"; Description: "Запустить панель и открыть браузер"; Flags: nowait postinstall skipifsilent shellexec

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PZControlPanel"; ValueData: """{app}\start_panel.bat"""; Flags: uninsdeletevalue; Tasks: autostart

[UninstallDelete]
Type: files; Name: "{app}\.env"
