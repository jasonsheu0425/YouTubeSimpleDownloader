$ErrorActionPreference = "Stop"

$ProjectDir = [IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))
$AppName = "YouTubeSimpleDownloader"
$Publisher = "Jason Test Signing"
$Subject = "CN=Jason YouTube Simple Downloader Test Signing"
$DistDir = Join-Path $ProjectDir "dist\$AppName"
$AppExe = Join-Path $DistDir "$AppName.exe"
$DistFfmpeg = Join-Path $DistDir "_internal\ffmpeg\ffmpeg.exe"
$Python = Join-Path $ProjectDir ".release-venv\Scripts\python.exe"
$IntegrityScript = Join-Path $ProjectDir "scripts\release_integrity.py"
$ArtifactCheck = Join-Path $ProjectDir "scripts\check_ffmpeg_artifact.py"
$QtCheck = Join-Path $ProjectDir "scripts\check_packaged_qt_runtime.py"
$TemplatePath = Join-Path $ProjectDir "installer\YouTubeSimpleDownloader.iss"
$OutputDir = Join-Path $ProjectDir "release"

$ProjectToml = Get-Content -Raw -LiteralPath (Join-Path $ProjectDir "pyproject.toml")
$VersionMatch = [regex]::Match($ProjectToml, '(?m)^version\s*=\s*"(?<version>[^"]+)"\s*$')
if (-not $VersionMatch.Success) {
    throw "Unable to read project version from pyproject.toml."
}
$Version = $VersionMatch.Groups["version"].Value
$PackageInit = Get-Content -Raw -LiteralPath (Join-Path $ProjectDir "src\ytsimpledownloader\__init__.py")
$RuntimeVersionMatch = [regex]::Match($PackageInit, '(?m)^__version__\s*=\s*"(?<version>[^"]+)"\s*$')
if (-not $RuntimeVersionMatch.Success -or $RuntimeVersionMatch.Groups["version"].Value -ne $Version) {
    throw "Runtime and package versions do not match."
}

$BaseName = "${AppName}_Setup_v$Version-inno-self-signed"
$InstallerFile = "$BaseName.exe"
$SbomFile = "$BaseName.sbom.cdx.json"
$ProvenanceFile = "$BaseName.provenance.json"
$CertificateFile = "Jason-YouTubeSimpleDownloader-TestSigning.cer"
$InstallerPath = Join-Path $OutputDir $InstallerFile
$SbomPath = Join-Path $OutputDir $SbomFile
$ProvenancePath = Join-Path $OutputDir $ProvenanceFile
$CertPath = Join-Path $OutputDir $CertificateFile

$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$ISCC = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (!$ISCC) {
    throw "ISCC.exe not found. Install Inno Setup 6 first."
}
$ISCCInstallDir = [IO.Path]::GetFullPath((Split-Path -Parent $ISCC)).TrimEnd('\')
$innoUninstallRoots = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
)
$registeredInnoInstallations = @(
    foreach ($uninstallRoot in $innoUninstallRoots) {
        if (Test-Path -LiteralPath $uninstallRoot) {
            foreach ($entryKey in Get-ChildItem -LiteralPath $uninstallRoot -ErrorAction SilentlyContinue) {
                $entry = Get-ItemProperty -LiteralPath $entryKey.PSPath -ErrorAction SilentlyContinue
                if ($entry.DisplayName -like "Inno Setup version *" -and $entry.InstallLocation) {
                    $registeredDir = [IO.Path]::GetFullPath($entry.InstallLocation).TrimEnd('\')
                    if ($registeredDir -ieq $ISCCInstallDir) {
                        [pscustomobject]@{
                            DisplayName = [string]$entry.DisplayName
                            DisplayVersion = [string]$entry.DisplayVersion
                            Publisher = [string]$entry.Publisher
                        }
                    }
                }
            }
        }
    }
)
if ($registeredInnoInstallations.Count -ne 1) {
    throw "Unable to uniquely match ISCC.exe to an installed Inno Setup registration."
}
$ISCCVersion = $registeredInnoInstallations[0].DisplayVersion
if ($ISCCVersion -notmatch '^\d+(?:\.\d+){1,3}$' -or
    $registeredInnoInstallations[0].DisplayName -cne "Inno Setup version $ISCCVersion" -or
    $registeredInnoInstallations[0].Publisher -cne "jrsoftware.org") {
    throw "The registered Inno Setup version is missing or inconsistent."
}
$ISCCSignature = Get-AuthenticodeSignature -FilePath $ISCC
if ($ISCCSignature.Status.ToString() -ne "Valid") {
    throw "The selected Inno Setup compiler does not have a valid Authenticode signature."
}
$ISCCSigner = $ISCCSignature.SignerCertificate.GetNameInfo(
    [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,
    $false
)
if ($ISCCSigner -cne "Pyrsys B.V.") {
    throw "The selected Inno Setup compiler has an unexpected Authenticode signer: $ISCCSigner"
}
foreach ($requiredPath in @($AppExe, $DistFfmpeg, $Python, $IntegrityScript, $ArtifactCheck, $QtCheck, $TemplatePath)) {
    if (!(Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required build input is missing: $([IO.Path]::GetFileName($requiredPath))"
    }
}
if (Test-Path -LiteralPath $InstallerPath -PathType Leaf) { throw "Refusing to overwrite existing installer: $InstallerFile" }
if (Test-Path -LiteralPath $SbomPath -PathType Leaf) { throw "Refusing to overwrite existing SBOM: $SbomFile" }
if (Test-Path -LiteralPath $ProvenancePath -PathType Leaf) { throw "Refusing to overwrite existing provenance: $ProvenanceFile" }
if (Test-Path -LiteralPath $CertPath -PathType Leaf) { throw "Refusing to overwrite existing public certificate: $CertificateFile" }

& $Python $IntegrityScript preflight --project-root $ProjectDir
if ($LASTEXITCODE -ne 0) { throw "Release source preflight failed with exit code $LASTEXITCODE." }
& $Python $ArtifactCheck $DistFfmpeg
if ($LASTEXITCODE -ne 0) { throw "Dist FFmpeg artifact verification failed with exit code $LASTEXITCODE." }
& $Python $QtCheck (Join-Path $DistDir "_internal")
if ($LASTEXITCODE -ne 0) { throw "Packaged Qt runtime verification failed with exit code $LASTEXITCODE." }

$QtCore = Get-ChildItem -LiteralPath $DistDir -Recurse -File -Filter "Qt6Core.dll" | Select-Object -First 1
if (!$QtCore) { throw "Bundled Qt6Core.dll was not found; refusing to build an incomplete SBOM." }
$QtVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($QtCore.FullName).ProductVersion
if ([string]::IsNullOrWhiteSpace($QtVersion)) {
    $QtVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($QtCore.FullName).FileVersion
}
if ([string]::IsNullOrWhiteSpace($QtVersion)) { throw "Unable to identify the bundled Qt version." }

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StagingRoot = Join-Path $OutputDir ".staging-$([guid]::NewGuid().ToString('N'))"
if (Test-Path -LiteralPath $StagingRoot) { throw "Staging path collision; refusing to reuse it." }
$AssetsDir = Join-Path $StagingRoot "assets"
$CompilerOutput = Join-Path $StagingRoot "output"
$PayloadDir = Join-Path $StagingRoot "payload"
$PayloadFfmpeg = Join-Path $PayloadDir "_internal\ffmpeg\ffmpeg.exe"
New-Item -ItemType Directory -Path $AssetsDir, $CompilerOutput, $PayloadDir | Out-Null

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

function Assert-ValidSignature([string]$Path, [string]$ExpectedSubject, [string]$ExpectedThumbprint) {
    $signature = Get-AuthenticodeSignature -FilePath $Path
    if ($signature.Status.ToString() -ne "Valid") {
        throw "Authenticode verification failed for $([IO.Path]::GetFileName($Path)): $($signature.Status)"
    }
    if (!$signature.SignerCertificate -or $signature.SignerCertificate.Subject -ne $ExpectedSubject) {
        throw "Unexpected Authenticode signer for $([IO.Path]::GetFileName($Path))."
    }
    if ($signature.SignerCertificate.Thumbprint -ne $ExpectedThumbprint) {
        throw "Authenticode signer certificate does not match the build certificate for $([IO.Path]::GetFileName($Path))."
    }
    return $signature
}

$PromotedInstaller = $false
$PromotedSbom = $false
$PromotedProvenance = $false
$PromotedCertificate = $false
$PromotionVerified = $false

try {
    Export-Certificate -Cert $cert -FilePath (Join-Path $AssetsDir $CertificateFile) | Out-Null
    Set-AuthenticodeSignature -FilePath $AppExe -Certificate $cert -HashAlgorithm SHA256 | Out-Null
    $appSignature = Assert-ValidSignature $AppExe $Subject $cert.Thumbprint

    Get-ChildItem -LiteralPath $DistDir -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $PayloadDir -Recurse -Force
    }
    if (!(Test-Path -LiteralPath (Join-Path $PayloadDir "$AppName.exe") -PathType Leaf)) {
        throw "Staged installer payload is missing the application executable."
    }
    & $Python $ArtifactCheck $PayloadFfmpeg
    if ($LASTEXITCODE -ne 0) { throw "Staged payload FFmpeg verification failed with exit code $LASTEXITCODE." }
    & $Python $QtCheck (Join-Path $PayloadDir "_internal")
    if ($LASTEXITCODE -ne 0) { throw "Staged payload Qt runtime verification failed with exit code $LASTEXITCODE." }
    $PayloadInventoryBefore = [string](& $Python $IntegrityScript inventory-hash --dist-dir $PayloadDir)
    if ($LASTEXITCODE -ne 0 -or $PayloadInventoryBefore -notmatch '^bundle-inventory-sha256=[A-F0-9]{64}$') {
        throw "Unable to capture the staged payload inventory digest."
    }

    Copy-Item -LiteralPath (Join-Path $ProjectDir "installer\LICENSE.txt") -Destination (Join-Path $AssetsDir "LICENSE.txt")
    Copy-Item -LiteralPath (Join-Path $ProjectDir "installer\README-INSTALLER.txt") -Destination (Join-Path $AssetsDir "README-INSTALLER.txt")
    $template = Get-Content -Raw -LiteralPath $TemplatePath
    $template = $template.Replace("@APP_VERSION@", $Version)
    $template = $template.Replace("@PROJECT_DIR@", $ProjectDir)
    $template = $template.Replace("@PAYLOAD_DIR@", $PayloadDir)
    $template = $template.Replace("@ASSET_DIR@", $AssetsDir)
    $template = $template.Replace("@OUTPUT_DIR@", $CompilerOutput)
    if ($template -match "@[A-Z_]+@") { throw "Unexpanded placeholder remains in staged Inno script." }
    $StagedIss = Join-Path $StagingRoot "YouTubeSimpleDownloader.iss"
    Set-Content -LiteralPath $StagedIss -Value $template -Encoding UTF8

    $StagedInstaller = Join-Path $CompilerOutput $InstallerFile
    $StagedSbom = Join-Path $StagingRoot $SbomFile
    $StagedProvenance = Join-Path $StagingRoot $ProvenanceFile
    $StagedCertificate = Join-Path $AssetsDir $CertificateFile

    $compilerStartInfo = [Diagnostics.ProcessStartInfo]::new()
    $compilerStartInfo.FileName = $ISCC
    # Arguments is supported by Windows PowerShell 5.1's .NET Framework runtime.
    $compilerStartInfo.Arguments = '"' + $StagedIss + '"'
    $compilerStartInfo.UseShellExecute = $false
    $compilerStartInfo.CreateNoWindow = $true
    $compilerStartInfo.RedirectStandardOutput = $true
    $compilerStartInfo.RedirectStandardError = $true
    $compilerProcess = [Diagnostics.Process]::new()
    $compilerProcess.StartInfo = $compilerStartInfo
    if (!$compilerProcess.Start()) { throw "Unable to start the Inno Setup compiler." }
    $compilerStdoutTask = $compilerProcess.StandardOutput.ReadToEndAsync()
    $compilerStderrTask = $compilerProcess.StandardError.ReadToEndAsync()
    $compilerProcess.WaitForExit()
    $compilerOutput = $compilerStdoutTask.GetAwaiter().GetResult() + "`n" +
        $compilerStderrTask.GetAwaiter().GetResult()
    if ($compilerProcess.ExitCode -ne 0) {
        throw "Inno Setup compile failed with exit code $($compilerProcess.ExitCode): $($compilerOutput.Trim())"
    }
    $compiledVersionMatch = [regex]::Match(
        $compilerOutput,
        '(?m)^Compiler engine version:\s*Inno Setup (?<version>\d+(?:\.\d+){1,3})\s*$'
    )
    if (!$compiledVersionMatch.Success) {
        throw "Inno Setup compiler output did not identify its engine version."
    }
    $compiledISCCVersion = $compiledVersionMatch.Groups["version"].Value
    if ($compiledISCCVersion -cne $ISCCVersion) {
        throw "Inno Setup compiler output version $compiledISCCVersion does not match registered version $ISCCVersion."
    }
    if (!(Test-Path -LiteralPath $StagedInstaller -PathType Leaf)) { throw "Inno Setup did not create the expected installer." }
    Set-AuthenticodeSignature -FilePath $StagedInstaller -Certificate $cert -HashAlgorithm SHA256 | Out-Null
    $installerSignature = Assert-ValidSignature $StagedInstaller $Subject $cert.Thumbprint

    $PayloadInventoryAfter = [string](& $Python $IntegrityScript inventory-hash --dist-dir $PayloadDir)
    if ($LASTEXITCODE -ne 0 -or $PayloadInventoryAfter -ne $PayloadInventoryBefore) {
        throw "The installer payload changed while Inno Setup was compiling it."
    }

    & $Python $IntegrityScript generate-sbom `
        --project-root $ProjectDir `
        --dist-dir $PayloadDir `
        --ffmpeg $PayloadFfmpeg `
        --output $StagedSbom `
        --qt-version $QtVersion `
        --inno-version $ISCCVersion
    if ($LASTEXITCODE -ne 0) { throw "SBOM generation/validation failed with exit code $LASTEXITCODE." }

    & $Python $IntegrityScript write-provenance `
        --project-root $ProjectDir `
        --installer $StagedInstaller `
        --sbom $StagedSbom `
        --staged-installer-script $StagedIss `
        --dist-dir $PayloadDir `
        --ffmpeg $PayloadFfmpeg `
        --output $StagedProvenance `
        --installer-filename $InstallerFile `
        --sbom-filename $SbomFile `
        --qt-version $QtVersion `
        --inno-version $ISCCVersion `
        --application-exe-status $appSignature.Status `
        --installer-status $installerSignature.Status `
        --signer-subject $Subject `
        --certificate-thumbprint $cert.Thumbprint
    if ($LASTEXITCODE -ne 0) { throw "Provenance generation/validation failed with exit code $LASTEXITCODE." }

    & $Python $IntegrityScript verify `
        --project-root $ProjectDir `
        --installer $StagedInstaller `
        --sbom $StagedSbom `
        --provenance $StagedProvenance `
        --ffmpeg $PayloadFfmpeg `
        --dist-dir $PayloadDir `
        --staged-installer-script $StagedIss
    if ($LASTEXITCODE -ne 0) { throw "Staged release integrity verification failed with exit code $LASTEXITCODE." }

    foreach ($destination in @($InstallerPath, $SbomPath, $ProvenancePath, $CertPath)) {
        if (Test-Path -LiteralPath $destination) { throw "Refusing to overwrite a release output: $([IO.Path]::GetFileName($destination))" }
    }
    Move-Item -LiteralPath $StagedSbom -Destination $SbomPath
    $PromotedSbom = $true
    Move-Item -LiteralPath $StagedProvenance -Destination $ProvenancePath
    $PromotedProvenance = $true
    Move-Item -LiteralPath $StagedCertificate -Destination $CertPath
    $PromotedCertificate = $true
    # The installer is the visible success artifact, so promote it only after
    # the staged installer, SBOM, provenance, signature, and ISS digest pass.
    Move-Item -LiteralPath $StagedInstaller -Destination $InstallerPath
    $PromotedInstaller = $true

    & $Python $IntegrityScript verify `
        --project-root $ProjectDir `
        --installer $InstallerPath `
        --sbom $SbomPath `
        --provenance $ProvenancePath `
        --ffmpeg $PayloadFfmpeg `
        --dist-dir $PayloadDir `
        --staged-installer-script $StagedIss
    if ($LASTEXITCODE -ne 0) { throw "Final release sidecar verification failed with exit code $LASTEXITCODE." }
    $null = Assert-ValidSignature $AppExe $Subject $cert.Thumbprint
    $null = Assert-ValidSignature $InstallerPath $Subject $cert.Thumbprint
    $PromotionVerified = $true

    $resolvedOutput = [IO.Path]::GetFullPath($OutputDir).TrimEnd('\') + '\'
    $resolvedStage = [IO.Path]::GetFullPath($StagingRoot)
    if (!$resolvedStage.StartsWith($resolvedOutput, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($resolvedStage) -notmatch '^\.staging-[0-9a-f]{32}$') {
        throw "Refusing to remove an unexpected installer staging path."
    }
    try {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force -ErrorAction Stop
    }
    catch {
        Write-Warning "Validated release outputs, but staging cleanup was incomplete; inspect: $resolvedStage"
    }

    Write-Host "Inno Setup: $ISCCVersion"
    Write-Host "Signer: $($cert.Subject)"
    Write-Host "Installer: $InstallerPath ($((Get-Item -LiteralPath $InstallerPath).Length) bytes)"
    Write-Host "SBOM: $SbomPath"
    Write-Host "Provenance: $ProvenancePath"
    Write-Host "Signature status: Valid"
}
catch {
    $buildFailure = $_
    if (!$PromotionVerified) {
        $rollback = @(
            [pscustomobject]@{ Promoted = $PromotedInstaller; Final = $InstallerPath; Staged = $StagedInstaller },
            [pscustomobject]@{ Promoted = $PromotedCertificate; Final = $CertPath; Staged = $StagedCertificate },
            [pscustomobject]@{ Promoted = $PromotedProvenance; Final = $ProvenancePath; Staged = $StagedProvenance },
            [pscustomobject]@{ Promoted = $PromotedSbom; Final = $SbomPath; Staged = $StagedSbom }
        )
        foreach ($item in $rollback) {
            if ($item.Promoted -and (Test-Path -LiteralPath $item.Final -PathType Leaf)) {
                try {
                    Move-Item -LiteralPath $item.Final -Destination $item.Staged -ErrorAction Stop
                }
                catch {
                    Write-Warning "Could not return promoted output to staging: $([IO.Path]::GetFileName($item.Final))"
                }
            }
        }
    }
    Write-Error $buildFailure
    Write-Host "Build staging retained for inspection: $StagingRoot"
    throw
}
