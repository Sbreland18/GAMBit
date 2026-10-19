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

[InstallDelete]
; Clear out files from the previous version before copying the new ones.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; No "skipifsilent": after a silent self-update GAMbit starts again automatically.
; /NOLAUNCH (for mass roll-outs) installs without starting GAMbit.
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall; Check: not NoLaunch

[Code]
function NoLaunch: Boolean;
var
  i: Integer;
begin
  Result := False;
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), '/NOLAUNCH') = 0 then
      Result := True;
end;
