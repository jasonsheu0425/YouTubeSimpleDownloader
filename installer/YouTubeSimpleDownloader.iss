#define MyAppName "YouTube Simple Downloader"
#define MyAppExeName "YouTubeSimpleDownloader.exe"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Jason Test Signing"

[Setup]
AppId={{E6DB2227-B12B-48EE-8583-7E3D1D47C2C5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\YouTubeSimpleDownloader
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=no
LicenseFile=E:\YouTubeSimpleDownloader\installer\LICENSE.txt
InfoAfterFile=E:\YouTubeSimpleDownloader\installer\README-INSTALLER.txt
OutputDir=E:\YouTubeSimpleDownloader\release
OutputBaseFilename=YouTubeSimpleDownloader_Setup_v0.2.0-inno-self-signed
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "E:\YouTubeSimpleDownloader\dist\YouTubeSimpleDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
