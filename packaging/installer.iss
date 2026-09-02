; PZ Server Control Panel — Inno Setup script (Sprint 6)
; Build: 1) python packaging/build_exe.py  2) ISCC packaging/installer.iss

#define MyAppName "PZ Control Panel"
#define MyAppVersion "3.17.0"
#define MyAppPublisher "MEATBALLS"
#define MyAppURL "https://github.com/meatsquad/MB"
#define MyBuildDir "..\dist\PZControlPanel"
#define MyOutputDir "Output"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\PZControlPanel
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
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Запускать панель при входе в Windows"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "templates\env.local.template"; DestDir: "{app}\packaging\templates"; Flags: ignoreversion
Source: "templates\env.remote.template"; DestDir: "{app}\packaging\templates"; Flags: ignoreversion
Source: "start_panel.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\start_panel.bat"; WorkingDir: "{app}"; IconFilename: "{app}\panel\static\assets\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\start_panel.bat"; WorkingDir: "{app}"; IconFilename: "{app}\panel\static\assets\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\start_panel.bat"; Description: "Запустить панель и открыть браузер"; Flags: nowait postinstall skipifsilent shellexec
Filename: "http://127.0.0.1:8000/"; Description: "Открыть http://127.0.0.1:8000/"; Flags: postinstall shellexec skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PZControlPanel"; ValueData: """{app}\start_panel.bat"""; Flags: uninsdeletevalue; Tasks: autostart

[Code]
var
  ModePage: TWizardPage;
  LocalRadio, RemoteRadio: TRadioButton;
  RemoteHostEdit: TEdit;
  SetupMode: Integer;

procedure InitializeWizard;
begin
  ModePage := CreateCustomPage(wpSelectDir, 'Режим установки', 'Выберите сценарий использования панели.');

  LocalRadio := TRadioButton.Create(ModePage);
  LocalRadio.Parent := ModePage.Surface;
  LocalRadio.Caption := 'Локальный сервер / Разработчик';
  LocalRadio.Left := 0;
  LocalRadio.Top := 16;
  LocalRadio.Width := ModePage.SurfaceWidth;
  LocalRadio.Checked := True;

  RemoteRadio := TRadioButton.Create(ModePage);
  RemoteRadio.Parent := ModePage.Surface;
  RemoteRadio.Caption := 'Клиент управления удалённым сервером (VPS / хостинг)';
  RemoteRadio.Left := 0;
  RemoteRadio.Top := 48;
  RemoteRadio.Width := ModePage.SurfaceWidth;

  RemoteHostEdit := TEdit.Create(ModePage);
  RemoteHostEdit.Parent := ModePage.Surface;
  RemoteHostEdit.Left := 0;
  RemoteHostEdit.Top := 88;
  RemoteHostEdit.Width := ModePage.SurfaceWidth;
  RemoteHostEdit.Text := 'your.vps.example';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ModePage.ID then
  begin
    if LocalRadio.Checked then
      SetupMode := 0
    else
      SetupMode := 1;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvPath, TemplatePath, HostVal: String;
  HostLine: String;
begin
  if CurStep = ssPostInstall then
  begin
    EnvPath := ExpandConstant('{app}\.env');
    if SetupMode = 0 then
      TemplatePath := ExpandConstant('{app}\packaging\templates\env.local.template')
    else
      TemplatePath := ExpandConstant('{app}\packaging\templates\env.remote.template');

    if FileExists(TemplatePath) then
    begin
      if not FileCopy(TemplatePath, EnvPath, False) then
        Log('Failed to copy env template');
    end;

    if SetupMode = 1 then
    begin
      HostVal := RemoteHostEdit.Text;
      if (HostVal <> '') and (HostVal <> 'your.vps.example') then
      begin
        HostLine := 'RCON_HOST=' + HostVal + #13#10 +
                    'FTP_HOST=' + HostVal + #13#10 +
                    'PUBLIC_HOST=' + HostVal + #13#10;
        SaveStringToFile(EnvPath, HostLine, True);
      end;
    end;
  end;
end;
