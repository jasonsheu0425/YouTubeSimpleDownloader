$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppName = "YouTubeSimpleDownloader"
$DisplayName = "YouTube Simple Downloader"
$Publisher = "Jason Test Signing"
$Version = "0.9.4"
$Subject = "CN=Jason YouTube Simple Downloader Test Signing"
$DistDir = Join-Path $ProjectDir "dist\$AppName"
$AppExe = Join-Path $DistDir "$AppName.exe"
$DistFfmpeg = Join-Path $DistDir "_internal\ffmpeg\ffmpeg.exe"
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$ArtifactCheck = Join-Path $ProjectDir "scripts\check_ffmpeg_artifact.py"
$IconPath = Join-Path $ProjectDir "src\ytsimpledownloader\assets\app_icon.ico"
$OutputDir = Join-Path $ProjectDir "release"
$CertPath = Join-Path $OutputDir "Jason-YouTubeSimpleDownloader-TestSigning.cer"
$IssPath = Join-Path $ProjectDir "installer\YouTubeSimpleDownloader.iss"
$InstallerPath = Join-Path $OutputDir "${AppName}_Setup_v$Version-inno-self-signed.exe"

$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$ISCC = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (!$ISCC) {
    throw "ISCC.exe not found. Install Inno Setup 6 first."
}
if (!(Test-Path $AppExe)) {
    throw "App EXE not found. Run build_exe.bat first: $AppExe"
}
if (!(Test-Path $Python)) {
    throw "Project Python not found. Run build_exe.bat first: $Python"
}
if (!(Test-Path $ArtifactCheck)) {
    throw "FFmpeg artifact verifier not found: $ArtifactCheck"
}
if (!(Test-Path $IconPath)) {
    throw "App icon not found: $IconPath"
}

& $Python $ArtifactCheck $DistFfmpeg
if ($LASTEXITCODE -ne 0) {
    throw "Dist FFmpeg artifact verification failed with exit code $LASTEXITCODE."
}

New-Item -ItemType Directory -Force -Path $OutputDir, (Split-Path $IssPath) | Out-Null

$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq $Subject } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if (!$cert) {
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -FriendlyName "Jason YouTube Simple Downloader Test Signing" `
        -CertStoreLocation Cert:\CurrentUser\My `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddYears(3)
}

Export-Certificate -Cert $cert -FilePath $CertPath | Out-Null

Set-AuthenticodeSignature -FilePath $AppExe -Certificate $cert -HashAlgorithm SHA256 | Out-Null
$appSig = Get-AuthenticodeSignature -FilePath $AppExe
if (!$appSig.SignerCertificate) {
    throw "App EXE signing failed."
}

$licensePath = Join-Path $ProjectDir "installer\LICENSE.txt"
$licenseNotice = @"
YouTube Simple Downloader

This application downloads public YouTube video or playlist URLs as audio, video, or both.

Responsible use:
- Public video and playlist URLs only.
- No login or cookie support.
- No private, paid, members-only, or DRM-protected content support.
- Use only for videos you have the right to save.

This installer bundles the MIT License for the application. The full source and license are available at:
https://github.com/jasonsheu0425/YouTubeSimpleDownloader
"@
$mitLicense = (Get-Content -Raw -Path (Join-Path $ProjectDir "LICENSE")).TrimEnd()
Set-Content -Path $licensePath -Encoding UTF8 -Value "$licenseNotice`r`n`r`n$mitLicense"

$readmePath = Join-Path $ProjectDir "installer\README-INSTALLER.txt"
Set-Content -Path $readmePath -Encoding UTF8 -Value @"
Install location

The default location is:
%LOCALAPPDATA%\Programs\YouTubeSimpleDownloader

The installer shows the destination page on every run and does not reuse a previous install location automatically.

Signing

This installer is self-signed for testing and friend-to-friend sharing.

Windows may still show a warning because this is not a paid trusted code-signing certificate.
The public test certificate is exported beside the installer:

Jason-YouTubeSimpleDownloader-TestSigning.cer
"@

$iss = @"
#define MyAppName "$DisplayName"
#define MyAppExeName "$AppName.exe"
#define MyAppVersion "$Version"
#define MyAppPublisher "$Publisher"
#define MyProjectDir "$ProjectDir"

[Setup]
AppId={{E6DB2227-B12B-48EE-8583-7E3D1D47C2C5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\$AppName
UsePreviousAppDir=no
DisableDirPage=no
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=no
LicenseFile={#MyProjectDir}\installer\LICENSE.txt
InfoAfterFile={#MyProjectDir}\installer\README-INSTALLER.txt
OutputDir={#MyProjectDir}\release
OutputBaseFilename=${AppName}_Setup_v$Version-inno-self-signed
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
Source: "{#MyProjectDir}\dist\$AppName\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal\imageio_ffmpeg\binaries"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
"@
Set-Content -Path $IssPath -Value $iss -Encoding UTF8

if (Test-Path $InstallerPath) {
    Remove-Item -LiteralPath $InstallerPath -Force
}

& $ISCC $IssPath
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compile failed with exit code $LASTEXITCODE"
}
if (!(Test-Path $InstallerPath)) {
    throw "Installer was not created: $InstallerPath"
}

Set-AuthenticodeSignature -FilePath $InstallerPath -Certificate $cert -HashAlgorithm SHA256 | Out-Null
$installerSig = Get-AuthenticodeSignature -FilePath $InstallerPath
if (!$installerSig.SignerCertificate) {
    throw "Installer signing failed."
}

Write-Host "Inno Setup:"
Write-Host "  $ISCC"
Write-Host "Certificate:"
Write-Host "  Subject: $($cert.Subject)"
Write-Host "  Thumbprint: $($cert.Thumbprint)"
Write-Host "  Exported: $CertPath"
Write-Host "Signed app:"
Write-Host "  $AppExe"
Write-Host "  Status: $($appSig.Status)"
Write-Host "Inno installer:"
Write-Host "  $InstallerPath"
Write-Host "  Status: $($installerSig.Status)"
