; Inno Setup script for spektralionkk (Windows app built on the open-source spektrafilm engine)
; Build: run build.ps1 in the repository root, which builds the app with PyInstaller into dist\ and then
; runs ISCC.exe on this file (paths below are relative to this folder). Output: release\.
; Saved as UTF-8 with BOM (Chinese text below).

#define AppName "spektralionkk"
#define AppVersion "1.4.0"
#define AppExe "spektralionkk.exe"
#define Src "..\dist\spektralionkk"
; build.ps1 -RepoUrl https://github.com/<you>/spektralionkk passes /DAppURL=... for Add/Remove Programs
#ifndef AppURL
  #define AppURL ""
#endif

[Setup]
AppId={{6E4C2B7A-5D1F-4C8E-9A3B-2F7D1E0C9B54}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
AppComments=Spectral film and print simulation. Engine: spektrafilm by Andrea Volpato
#if AppURL != ""
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
#endif
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Same AppId as the app's old name (sprktralionkk): installing replaces it. Don't reuse its folder / menu group.
UsePreviousAppDir=no
UsePreviousGroup=no
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\app\assets\spektralionkk.ico
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
LicenseFile={#Src}\LICENSE
OutputDir=..\release
OutputBaseFilename={#AppName}-{#AppVersion}-setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
; Ask for the installer language (English / Simplified Chinese), preselecting the Windows UI language
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Official Inno Setup translation (jrsoftware/issrc, Files/Languages/ChineseSimplified.isl), unchanged
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[CustomMessages]
english.SelfTest=%1 self-test
chinesesimplified.SelfTest=%1 自检
english.ReadMe=Read me
chinesesimplified.ReadMe=说明 (英文)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Remove files from older builds (the 0.3.x napari-based app) before installing.
Type: filesandordirs; Name: "{app}\_internal"
; The app was called "sprktralionkk" up to 1.4.0: remove that installation, its shortcuts and caches.
; (Photo edits / library are not touched; the app copies them to its new data folder on first start.)
Type: filesandordirs; Name: "{autopf}\sprktralionkk"
Type: filesandordirs; Name: "{autoprograms}\sprktralionkk"
Type: files; Name: "{autodesktop}\sprktralionkk.lnk"
Type: filesandordirs; Name: "{localappdata}\sprktralionkk\numba_cache"
Type: files; Name: "{localappdata}\sprktralionkk\sprktralionkk.log"
Type: files; Name: "{localappdata}\sprktralionkk\selftest.txt"

[Files]
Source: "{#Src}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
; The language picked in this installer is also the app's interface language ("english" / "chinesesimplified").
; The app can change it later (View > Language), which writes the same value.
Root: HKCU; Subkey: "Software\{#AppName}"; ValueType: string; ValueName: "Language"; ValueData: "{language}"; Flags: uninsdeletevalue uninsdeletekeyifempty
; The old name's setting is replaced by the one above.
Root: HKCU; Subkey: "Software\sprktralionkk"; ValueType: none; Flags: deletekey

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:SelfTest,{#AppName}}"; Filename: "{app}\{#AppExe}"; Parameters: "--selftest"
Name: "{group}\{cm:ReadMe}"; Filename: "{app}\README-spektralionkk.txt"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\{#AppName}\numba_cache"
Type: files; Name: "{localappdata}\{#AppName}\spektralionkk.log"
Type: files; Name: "{localappdata}\{#AppName}\selftest.txt"
