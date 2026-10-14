#define MyAppName "YouTube Simple Downloader"
#define MyAppExeName "YouTubeSimpleDownloader.exe"
#define MyAppVersion "@APP_VERSION@"
#define MyAppPublisher "Jason Test Signing"
#define MyProjectDir "@PROJECT_DIR@"
#define MyPayloadDir "@PAYLOAD_DIR@"
#define MyInstallerAssetsDir "@ASSET_DIR@"
#define MyOutputDir "@OUTPUT_DIR@"

[Setup]
AppId={{E6DB2227-B12B-48EE-8583-7E3D1D47C2C5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\YouTubeSimpleDownloader
UsePreviousAppDir=no
DisableDirPage=no
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=no
LicenseFile={#MyInstallerAssetsDir}\LICENSE.txt
InfoAfterFile={#MyInstallerAssetsDir}\README-INSTALLER.txt
OutputDir={#MyOutputDir}
OutputBaseFilename=YouTubeSimpleDownloader_Setup_v{#MyAppVersion}-inno-self-signed
SetupIconFile={#MyProjectDir}\src\ytsimpledownloader\assets\app_icon.ico
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
Source: "{#MyPayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal\imageio_ffmpeg\binaries"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
