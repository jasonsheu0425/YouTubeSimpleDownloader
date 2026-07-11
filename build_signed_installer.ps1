$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$innoScript = Join-Path $projectDir "build_inno_installer.ps1"

Write-Host "build_signed_installer.ps1 now delegates to the supported Inno Setup installer."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $innoScript
exit $LASTEXITCODE
