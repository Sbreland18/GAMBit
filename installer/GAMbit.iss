; Inno Setup script for GAMbit.
; The Builder GUI passes the version:  ISCC.exe /DMyAppVersion=1.2.0 installer\GAMbit.iss

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "GAMbit"
#define MyAppExe "GAMbit.exe"
#define MyAppPublisher "Spencer Breland"
#define MyAppURL "https://github.com/Sbreland18/GAMbit"

[Setup]
; Keep this AppId the same forever so updates replace the old install.
AppId={{6F1C2B7E-9A4D-4E1B-8C3F-2D5A7B9E0C41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install by default, so the app can update itself without an admin prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist\installer
OutputBaseFilename=GAMbit-Setup-{#MyAppVersion}
SetupIconFile=..\assets\gambit.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; The Builder passes /DSIGN=1 and /Sgambitsign=... when code signing is turned on,
; so both the installer and the uninstaller are signed.
#ifdef SIGN
SignTool=gambitsign
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\GAMbit\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Optional deployment settings placed next to the installer (see README → Rolling out)
Source: "{src}\gambit-deploy.json"; DestDir: "{app}"; Flags: external skipifsourcedoesntexist ignoreversion

; No [InstallDelete] of _internal: deleting it while any GAMbit (or a scheduled
; background task) still had files open left a half-deleted install that wouldn't start.
; [Code] below closes every GAMbit first, moves the old _internal aside, and puts it back
; if the update doesn't finish.

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal.old"

[Icons]
; AppUserModelID matches the one GAMbit sets at start-up, so Windows ties the taskbar
; button (and pinning) to this shortcut and its icon.
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\{#MyAppExe}"; AppUserModelID: "GAMbit.App"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\{#MyAppExe}"; AppUserModelID: "GAMbit.App"; Tasks: desktopicon

[Run]
; No "skipifsilent": after a silent self-update GAMbit starts again automatically.
; /NOLAUNCH (for mass roll-outs) installs without starting GAMbit.
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall; Check: not NoLaunch

[Code]
var
  InstallOk: Boolean;

function AppDirOrEmpty: String;
begin
  try
    Result := ExpandConstant('{app}');
  except
    Result := '';
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { close every running GAMbit – the window and any background task – so no file is
    locked while the new version is copied }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM GAMbit.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Sleep(1500);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  App: String;
begin
  App := AppDirOrEmpty;
  if App = '' then
    Exit;
  if CurStep = ssInstall then
  begin
    if DirExists(App + '\_internal.old') then
      DelTree(App + '\_internal.old', True, True, True);
    { move the old files aside (removes leftovers from older versions); if that isn't
      possible the new files are simply copied over the old ones }
    if DirExists(App + '\_internal') then
      RenameFile(App + '\_internal', App + '\_internal.old');
  end;
  if CurStep = ssPostInstall then
  begin
    InstallOk := True;
    DelTree(App + '\_internal.old', True, True, True);
  end;
end;

procedure DeinitializeSetup;
var
  App: String;
begin
  { the update didn't finish: put the previous version back so GAMbit still opens }
  App := AppDirOrEmpty;
  if (not InstallOk) and (App <> '') and DirExists(App + '\_internal.old') then
  begin
    DelTree(App + '\_internal', True, True, True);
    RenameFile(App + '\_internal.old', App + '\_internal');
  end;
end;

function NoLaunch: Boolean;
var
  i: Integer;
begin
  Result := False;
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), '/NOLAUNCH') = 0 then
      Result := True;
end;
