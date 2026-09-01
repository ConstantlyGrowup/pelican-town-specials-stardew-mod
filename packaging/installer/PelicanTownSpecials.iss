; Pelican Town Specials per-user Windows installer (Milestone 7 Task 23).
;
; Wraps the validated PyInstaller onedir bundle. Requires no administrator
; rights: installs per-user under {localappdata}\Programs, creates a required
; start-menu shortcut (Gus icon) and an optional desktop shortcut, and its
; uninstaller removes program files and shortcuts while leaving the app-data
; directory (%LOCALAPPDATA%\PelicanTownSpecials) untouched.
;
; PtsBundleDir / PtsOutputDir / PtsAppVersion are injected by
; scripts/build_installer.ps1 via ISCC /D defines; the defaults below make a
; plain `ISCC PelicanTownSpecials.iss` work from packaging/installer.

#ifndef PtsAppVersion
  #define PtsAppVersion "1.5.2"
#endif
#ifndef PtsBundleDir
  #define PtsBundleDir "..\..\dist\PelicanTownSpecials-windows-x64"
#endif
#ifndef PtsOutputDir
  #define PtsOutputDir "..\..\dist\installer"
#endif

[Setup]
AppId={{F3A6C7E2-4B91-4E0D-9C6A-8D5F2B1A7C43}
AppName=Pelican Town Specials
AppVersion={#PtsAppVersion}
AppVerName=Pelican Town Specials {#PtsAppVersion}
AppPublisher=Pelican Town Specials
UninstallDisplayName=Pelican Town Specials
DefaultDirName={localappdata}\Programs\PelicanTownSpecials
DefaultGroupName=Pelican Town Specials
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
SetupIconFile=..\..\packaging\assets\pelican-town-specials.ico
UninstallDisplayIcon={app}\PelicanTownSpecials.exe
OutputDir={#PtsOutputDir}
OutputBaseFilename=PelicanTownSpecials-Setup-v{#PtsAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#PtsAppVersion}.0
VersionInfoProductName=Pelican Town Specials
VersionInfoProductVersion={#PtsAppVersion}
VersionInfoDescription=Pelican Town Specials installer

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#PtsBundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Pelican Town Specials"; Filename: "{app}\PelicanTownSpecials.exe"; WorkingDir: "{app}"; IconFilename: "{app}\PelicanTownSpecials.exe"; Comment: "Pelican Town Specials"
Name: "{autodesktop}\Pelican Town Specials"; Filename: "{app}\PelicanTownSpecials.exe"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\PelicanTownSpecials.exe"; Comment: "Pelican Town Specials"

[Run]
Filename: "{app}\PelicanTownSpecials.exe"; Description: "{cm:LaunchProgram,Pelican Town Specials}"; Flags: nowait postinstall skipifsilent
