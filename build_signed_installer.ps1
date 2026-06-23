$ErrorActionPreference = "Stop"

$ProjectDir = "E:\YouTubeSimpleDownloader"
$AppName = "YouTubeSimpleDownloader"
$DisplayName = "YouTube Simple Downloader"
$Publisher = "Jason Test Signing"
$Version = "0.5.1"
$Subject = "CN=Jason YouTube Simple Downloader Test Signing"
$SevenZip = "C:\Program Files\7-Zip\7z.exe"
$SevenZipSfx = "C:\Program Files\7-Zip\7z.sfx"
$DistDir = Join-Path $ProjectDir "dist\$AppName"
$AppExe = Join-Path $DistDir "$AppName.exe"
$InstallerDir = Join-Path $ProjectDir "installer"
$PayloadDir = Join-Path $InstallerDir "payload"
$PayloadAppDir = Join-Path $PayloadDir "app"
$OutputDir = Join-Path $ProjectDir "release"
$ArchivePath = Join-Path $InstallerDir "$AppName.7z"
$ConfigPath = Join-Path $InstallerDir "sfx-config.txt"
$InstallerPath = Join-Path $OutputDir "${AppName}_Setup_v$Version-self-signed.exe"
$CertPath = Join-Path $OutputDir "Jason-YouTubeSimpleDownloader-TestSigning.cer"

if (!(Test-Path $SevenZip)) {
    throw "7-Zip not found: $SevenZip"
}
if (!(Test-Path $SevenZipSfx)) {
    throw "7-Zip SFX module not found: $SevenZipSfx"
}
if (!(Test-Path $AppExe)) {
    throw "App EXE not found. Run build_exe.bat first: $AppExe"
}

New-Item -ItemType Directory -Force -Path $InstallerDir, $OutputDir | Out-Null

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
if ($appSig.Status -notin @("Valid", "UnknownError")) {
    throw "App EXE signing failed: $($appSig.Status) $($appSig.StatusMessage)"
}

if (Test-Path $PayloadDir) {
    Remove-Item -LiteralPath $PayloadDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PayloadAppDir | Out-Null
Copy-Item -Path (Join-Path $DistDir "*") -Destination $PayloadAppDir -Recurse -Force

$installCmd = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
'@
Set-Content -Path (Join-Path $PayloadDir "install.cmd") -Value $installCmd -Encoding ASCII

$installPs1 = @"
`$ErrorActionPreference = "Stop"

`$AppName = "$AppName"
`$DisplayName = "$DisplayName"
`$Publisher = "$Publisher"
`$Version = "$Version"
`$InstallDir = Join-Path `$env:LOCALAPPDATA "Programs\`$AppName"
`$SourceAppDir = Join-Path `$PSScriptRoot "app"
`$ExePath = Join-Path `$InstallDir "`$AppName.exe"
`$StartMenuDir = Join-Path `$env:APPDATA "Microsoft\Windows\Start Menu\Programs\`$DisplayName"
`$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "`$DisplayName.lnk"
`$StartShortcut = Join-Path `$StartMenuDir "`$DisplayName.lnk"

New-Item -ItemType Directory -Force -Path `$InstallDir, `$StartMenuDir | Out-Null
Copy-Item -Path (Join-Path `$SourceAppDir "*") -Destination `$InstallDir -Recurse -Force

`$uninstallPs1 = @'
`$ErrorActionPreference = "Stop"
`$AppName = "$AppName"
`$DisplayName = "$DisplayName"
`$InstallDir = Join-Path `$env:LOCALAPPDATA "Programs\`$AppName"
`$StartMenuDir = Join-Path `$env:APPDATA "Microsoft\Windows\Start Menu\Programs\`$DisplayName"
`$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "`$DisplayName.lnk"
Remove-Item -LiteralPath `$DesktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath `$StartMenuDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\`$AppName" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath `$InstallDir -Recurse -Force -ErrorAction SilentlyContinue
'@
Set-Content -Path (Join-Path `$InstallDir "uninstall.ps1") -Value `$uninstallPs1 -Encoding UTF8

`$shell = New-Object -ComObject WScript.Shell
foreach (`$shortcutPath in @(`$DesktopShortcut, `$StartShortcut)) {
    `$shortcut = `$shell.CreateShortcut(`$shortcutPath)
    `$shortcut.TargetPath = `$ExePath
    `$shortcut.WorkingDirectory = `$InstallDir
    `$shortcut.IconLocation = "`$ExePath,0"
    `$shortcut.Save()
}

`$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\`$AppName"
New-Item -Path `$uninstallKey -Force | Out-Null
Set-ItemProperty -Path `$uninstallKey -Name DisplayName -Value `$DisplayName
Set-ItemProperty -Path `$uninstallKey -Name DisplayVersion -Value `$Version
Set-ItemProperty -Path `$uninstallKey -Name Publisher -Value `$Publisher
Set-ItemProperty -Path `$uninstallKey -Name InstallLocation -Value `$InstallDir
Set-ItemProperty -Path `$uninstallKey -Name DisplayIcon -Value `$ExePath
Set-ItemProperty -Path `$uninstallKey -Name UninstallString -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ```"`$InstallDir\uninstall.ps1```""
Set-ItemProperty -Path `$uninstallKey -Name NoModify -Value 1 -Type DWord
Set-ItemProperty -Path `$uninstallKey -Name NoRepair -Value 1 -Type DWord

Start-Process -FilePath `$ExePath
"@
Set-Content -Path (Join-Path $PayloadDir "install.ps1") -Value $installPs1 -Encoding UTF8

if (Test-Path $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath -Force
}
Push-Location $PayloadDir
try {
    & $SevenZip a -t7z -mx=9 $ArchivePath ".\*" | Out-Null
} finally {
    Pop-Location
}

$config = @'
;!@Install@!UTF-8!
Title="YouTube Simple Downloader Installer"
BeginPrompt="Install YouTube Simple Downloader?"
RunProgram="install.cmd"
GUIMode="1"
;!@InstallEnd@!
'@
Set-Content -Path $ConfigPath -Value $config -Encoding UTF8

if (Test-Path $InstallerPath) {
    Remove-Item -LiteralPath $InstallerPath -Force
}

$sfxBytes = [System.IO.File]::ReadAllBytes($SevenZipSfx)
$configBytes = [System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw -Path $ConfigPath))
$archiveBytes = [System.IO.File]::ReadAllBytes($ArchivePath)
$out = [System.IO.File]::Create($InstallerPath)
try {
    $out.Write($sfxBytes, 0, $sfxBytes.Length)
    $out.Write($configBytes, 0, $configBytes.Length)
    $out.Write($archiveBytes, 0, $archiveBytes.Length)
} finally {
    $out.Close()
}

Set-AuthenticodeSignature -FilePath $InstallerPath -Certificate $cert -HashAlgorithm SHA256 | Out-Null
$installerSig = Get-AuthenticodeSignature -FilePath $InstallerPath

Write-Host "Certificate:"
Write-Host "  Subject: $($cert.Subject)"
Write-Host "  Thumbprint: $($cert.Thumbprint)"
Write-Host "  Exported: $CertPath"
Write-Host "Signed app:"
Write-Host "  $AppExe"
Write-Host "  Status: $($appSig.Status)"
Write-Host "Installer:"
Write-Host "  $InstallerPath"
Write-Host "  Status: $($installerSig.Status)"
