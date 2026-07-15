#define AppName "FuelOpt"
#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
#define AppPublisher "FuelOpt"
#define AppExeName "FuelOpt.exe"
#define AppIconSource "..\assets\fuelopt.ico"

[Setup]
AppId={{0EA78328-E3EB-48EF-A92C-B87491202B14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
OutputDir=..\dist\installer
OutputBaseFilename=FuelOpt-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no
Uninstallable=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=FuelOpt installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
SetupIconFile={#AppIconSource}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
spanish.RefreshTitle=Actualización del catálogo
english.RefreshTitle=Catalog refresh
spanish.RefreshSubtitle=Selecciona la frecuencia de actualización
english.RefreshSubtitle=Choose the refresh frequency
spanish.RefreshDescription=FuelOpt actualiza los precios directamente sin abrir el servidor. Puedes cambiar esta opción después.
english.RefreshDescription=FuelOpt refreshes prices directly without starting the server. You can change this setting later.
spanish.Refresh1h=Cada 1 hora
english.Refresh1h=Every 1 hour
spanish.Refresh2h=Cada 2 horas
english.Refresh2h=Every 2 hours
spanish.Refresh4h=Cada 4 horas
english.Refresh4h=Every 4 hours
spanish.Refresh8h=Cada 8 horas
english.Refresh8h=Every 8 hours
spanish.Refresh12h=Cada 12 horas
english.Refresh12h=Every 12 hours
spanish.Refresh24h=Cada 24 horas (recomendado)
english.Refresh24h=Every 24 hours (recommended)
spanish.RefreshOnOpen=Al abrir FuelOpt
english.RefreshOnOpen=When FuelOpt opens
spanish.RefreshManual=Solo manual
english.RefreshManual=Manual only
spanish.InvalidRefresh=El valor de /REFRESH no es válido. Valores permitidos: 1h, 2h, 4h, 8h, 12h, 24h, on_open, manual.
english.InvalidRefresh=The /REFRESH value is invalid. Allowed values: 1h, 2h, 4h, 8h, 12h, 24h, on_open, manual.
spanish.RefreshFailed=FuelOpt se instaló, pero no pudo guardar la frecuencia de actualización. Código: %1
english.RefreshFailed=FuelOpt was installed, but it could not save the refresh frequency. Code: %1
spanish.CloseFailed=No se pudo cerrar FuelOpt de forma segura. Cierra la aplicación e inténtalo de nuevo.
english.CloseFailed=FuelOpt could not be closed safely. Close the application and try again.
spanish.TaskRemoveFailed=No se pudo eliminar de forma segura la tarea programada de FuelOpt.
english.TaskRemoveFailed=The FuelOpt scheduled task could not be removed safely.
spanish.RemoveUserData=Eliminar también mis datos, configuración y precios almacenados
english.RemoveUserData=Also remove my data, settings and stored prices
spanish.LaunchFuelOpt=Ejecutar FuelOpt
english.LaunchFuelOpt=Run FuelOpt

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\FuelOpt\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#AppExeName}"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchFuelOpt}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
var
  RefreshPage: TInputOptionWizardPage;
  RemoveDataCheckBox: TNewCheckBox;
  RequestedRefresh: String;
  RemoveDataSilently: Boolean;

function IsAllowedRefresh(Value: String): Boolean;
begin
  Value := Lowercase(Trim(Value));
  Result := (Value = '1h') or (Value = '2h') or (Value = '4h') or
    (Value = '8h') or (Value = '12h') or (Value = '24h') or
    (Value = 'on_open') or (Value = 'manual');
end;

function RefreshIntervalFromIndex(Index: Integer): String;
begin
  case Index of
    0: Result := '1h';
    1: Result := '2h';
    2: Result := '4h';
    3: Result := '8h';
    4: Result := '12h';
    5: Result := '24h';
    6: Result := 'on_open';
    7: Result := 'manual';
  else
    Result := '24h';
  end;
end;

function RefreshIndexFromInterval(Value: String): Integer;
begin
  Value := Lowercase(Trim(Value));
  if Value = '1h' then Result := 0
  else if Value = '2h' then Result := 1
  else if Value = '4h' then Result := 2
  else if Value = '8h' then Result := 3
  else if Value = '12h' then Result := 4
  else if Value = '24h' then Result := 5
  else if Value = 'on_open' then Result := 6
  else if Value = 'manual' then Result := 7
  else Result := 5;
end;

function InitializeSetup: Boolean;
begin
  RequestedRefresh := ExpandConstant('{param:REFRESH|__absent__}');
  if RequestedRefresh <> '__absent__' then
  begin
    RequestedRefresh := Lowercase(Trim(RequestedRefresh));
    if not IsAllowedRefresh(RequestedRefresh) then
    begin
      Log('Rejected invalid /REFRESH parameter.');
      SuppressibleMsgBox(ExpandConstant('{cm:InvalidRefresh}'), mbError, MB_OK, IDOK);
      Result := False;
      exit;
    end;
  end;
  Result := True;
end;

procedure InitializeWizard;
begin
  RefreshPage := CreateInputOptionPage(
    wpSelectTasks,
    ExpandConstant('{cm:RefreshTitle}'),
    ExpandConstant('{cm:RefreshSubtitle}'),
    ExpandConstant('{cm:RefreshDescription}'),
    True,
    False
  );
  RefreshPage.Add(ExpandConstant('{cm:Refresh1h}'));
  RefreshPage.Add(ExpandConstant('{cm:Refresh2h}'));
  RefreshPage.Add(ExpandConstant('{cm:Refresh4h}'));
  RefreshPage.Add(ExpandConstant('{cm:Refresh8h}'));
  RefreshPage.Add(ExpandConstant('{cm:Refresh12h}'));
  RefreshPage.Add(ExpandConstant('{cm:Refresh24h}'));
  RefreshPage.Add(ExpandConstant('{cm:RefreshOnOpen}'));
  RefreshPage.Add(ExpandConstant('{cm:RefreshManual}'));

  if RequestedRefresh = '__absent__' then
    RequestedRefresh := GetPreviousData('RefreshInterval', '24h');
  if not IsAllowedRefresh(RequestedRefresh) then
    RequestedRefresh := '24h';
  RefreshPage.SelectedValueIndex := RefreshIndexFromInterval(RequestedRefresh);
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'RefreshInterval',
    RefreshIntervalFromIndex(RefreshPage.SelectedValueIndex));
end;

function RunFuelOptCommand(Parameters: String; var ResultCode: Integer): Boolean;
begin
  Result := Exec(
    ExpandConstant('{app}\{#AppExeName}'),
    Parameters,
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\{#AppExeName}')) then
    if (not RunFuelOptCommand('--shutdown-existing', ResultCode)) or (ResultCode <> 0) then
      Result := ExpandConstant('{cm:CloseFailed}');
end;

procedure ConfigureRefresh;
var
  ResultCode: Integer;
  Interval: String;
begin
  Interval := RefreshIntervalFromIndex(RefreshPage.SelectedValueIndex);
  if (not RunFuelOptCommand('--configure-refresh --interval ' + Interval, ResultCode)) or
    (ResultCode <> 0) then
    SuppressibleMsgBox(FmtMessage(ExpandConstant('{cm:RefreshFailed}'), [IntToStr(ResultCode)]),
      mbError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    ConfigureRefresh;
end;

function InitializeUninstall: Boolean;
var
  ResultCode: Integer;
begin
  RemoveDataSilently := Lowercase(Trim(ExpandConstant('{param:REMOVEDATA|0}'))) = '1';
  Result := False;
  if (not RunFuelOptCommand('--shutdown-existing', ResultCode)) or (ResultCode <> 0) then
  begin
    SuppressibleMsgBox(ExpandConstant('{cm:CloseFailed}'), mbError, MB_OK, IDOK);
    exit;
  end;
  if (not RunFuelOptCommand('--remove-refresh-task', ResultCode)) or (ResultCode <> 0) then
  begin
    SuppressibleMsgBox(ExpandConstant('{cm:TaskRemoveFailed}'), mbError, MB_OK, IDOK);
    exit;
  end;
  Result := True;
end;

procedure InitializeUninstallProgressForm;
begin
  RemoveDataCheckBox := TNewCheckBox.Create(UninstallProgressForm);
  RemoveDataCheckBox.Parent := UninstallProgressForm.InnerPage;
  RemoveDataCheckBox.Left := ScaleX(0);
  RemoveDataCheckBox.Top := UninstallProgressForm.StatusLabel.Top + ScaleY(48);
  RemoveDataCheckBox.Width := UninstallProgressForm.InnerPage.ClientWidth;
  RemoveDataCheckBox.Caption := ExpandConstant('{cm:RemoveUserData}');
  RemoveDataCheckBox.Checked := RemoveDataSilently;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    UserDataPath := ExpandConstant('{localappdata}\FuelOpt');
    if RemoveDataSilently or ((RemoveDataCheckBox <> nil) and RemoveDataCheckBox.Checked) then
    begin
      Log('Removing FuelOpt user data by explicit request.');
      DelTree(UserDataPath, True, True, True);
    end
    else
      Log('Preserving FuelOpt user data.');
  end;
end;
