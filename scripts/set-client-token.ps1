param([Parameter(Mandatory=$true)][string]$InstallDirectory)
$ErrorActionPreference='Stop'
if (-not (Test-Path -LiteralPath $InstallDirectory -PathType Container)) { throw 'Install directory does not exist.' }
Add-Type -AssemblyName System.Security
$secret=Read-Host 'Archive service token' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $encrypted=[Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($plain),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    [IO.File]::WriteAllBytes((Join-Path $InstallDirectory 'archive-token.dpapi'),$encrypted)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $plain=$null
    $secret.Dispose()
}
Write-Output 'Credential encrypted for the current Windows account.'
