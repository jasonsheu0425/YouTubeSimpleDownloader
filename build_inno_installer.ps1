$ErrorActionPreference = "Stop"

$ProjectDir = "E:\YouTubeSimpleDownloader"
$AppName = "YouTubeSimpleDownloader"
$DisplayName = "YouTube Simple Downloader"
$Publisher = "Jason Test Signing"
$Version = "0.2.1"
$Subject = "CN=Jason YouTube Simple Downloader Test Signing"
$DistDir = Join-Path $ProjectDir "dist\$AppName"
$AppExe = Join-Path $DistDir "$AppName.exe"
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
Set-Content -Path $licensePath -Encoding UTF8 -Value @"
YouTube Simple Downloader

This is a small personal utility for downloading one or more public YouTube video URLs as MP3, MP4, or both.

Current limitations:
- Public video URLs only.
- No playlist support.
- No login or cookie support.
- Use only for videos you have the right to save.
"@

$readmePath = Join-Path $ProjectDir "installer\README-INSTALLER.txt"
Set-Content -Path $readmePath -Encoding UTF8 -Value @"
This installer is self-signed for friend-to-friend testing.

Windows may still show a warning because this is not a paid trusted code-signing certificate.
The public test certificate is exported beside the installer:

Jason-YouTubeSimpleDownloader-TestSigning.cer
"@

$iss = @"
#define MyAppName "$DisplayName"
#define MyAppExeName "$AppName.exe"
#define MyAppVersion "$Version"
#define MyAppPublisher "$Publisher"

[Setup]
AppId={{E6DB2227-B12B-48EE-8583-7E3D1D47C2C5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\$AppName
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=no
LicenseFile=$licensePath
InfoAfterFile=$readmePath
OutputDir=$OutputDir
OutputBaseFilename=${AppName}_Setup_v$Version-inno-self-signed
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
Source: "$DistDir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
