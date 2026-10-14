param(
    [Parameter(Mandatory = $true)][ValidateSet('Sign', 'Verify')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$ExpectedThumbprint
)

$ErrorActionPreference = 'Stop'
$Subject = 'CN=Jason YouTube Simple Downloader Test Signing'
$resolved = [IO.Path]::GetFullPath($Path)
if (!(Test-Path -LiteralPath $resolved -PathType Leaf)) {
    throw 'Application executable is missing.'
}

if ($Mode -eq 'Sign') {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -ceq $Subject } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
    if (!$cert) {
        $cert = New-SelfSignedCertificate `
            -Type CodeSigningCert `
            -Subject $Subject `
            -FriendlyName 'Jason YouTube Simple Downloader Test Signing' `
            -CertStoreLocation Cert:\CurrentUser\My `
            -KeyAlgorithm RSA `
            -KeyLength 3072 `
            -HashAlgorithm SHA256 `
            -NotAfter (Get-Date).AddYears(3)
    }
    Set-AuthenticodeSignature -FilePath $resolved -Certificate $cert -HashAlgorithm SHA256 | Out-Null
    $ExpectedThumbprint = $cert.Thumbprint
}

$signature = Get-AuthenticodeSignature -FilePath $resolved
if ($signature.Status.ToString() -cne 'Valid' -or !$signature.SignerCertificate) {
    throw 'Application Authenticode signature is not valid.'
}
if ($signature.SignerCertificate.Subject -cne $Subject) {
    throw 'Application Authenticode signer subject is unexpected.'
}
$thumbprint = $signature.SignerCertificate.Thumbprint
if ($ExpectedThumbprint -and $thumbprint -cne $ExpectedThumbprint) {
    throw 'Application Authenticode signer certificate does not match.'
}
if (!(Test-Path -LiteralPath "Cert:\CurrentUser\My\$thumbprint" -PathType Leaf)) {
    throw 'Application signing certificate is absent from the current user store.'
}
Write-Output $thumbprint
