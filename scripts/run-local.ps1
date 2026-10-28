param([Parameter(Mandatory=$true)][string[]]$Folders,[string]$ClientInstallDirectory='C:\ArchiveSearch')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$state=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Seekr\service'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$environmentPath=Join-Path $state 'venv'
if (-not (Test-Path (Join-Path $environmentPath 'Scripts\python.exe'))) {
    python -m venv $environmentPath
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
}
$python=Join-Path $environmentPath 'Scripts\python.exe'
& $python -m pip install -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install local service dependencies.' }
$settingsPath=Join-Path $state 'settings.json'
if (-not (Test-Path $settingsPath)) {
    $sources=@();$n=0
    foreach ($folder in $Folders) {
        $resolved=(Resolve-Path -LiteralPath $folder).Path
        if (-not (Test-Path -LiteralPath $resolved -PathType Container)) { throw 'Each index source must be a directory.' }
        $n++;$sources+=@{id="Local$n";path=$resolved;client_path=$resolved;enabled=$true}
    }
    @{version=1;sources=$sources;dedupe=@{enabled=$false};docmost=@{enabled=$false;mcp_url='';semantic_url='';app_url='';page_url_template=''}} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $settingsPath -Encoding UTF8
}
Add-Type -AssemblyName System.Security
$credential=Join-Path $ClientInstallDirectory 'archive-token.dpapi'
if (-not (Test-Path $credential)) { throw 'Provision a client token first with set-client-token.ps1.' }
$env:ARCHIVE_TOKEN=[Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($credential),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)).Trim()
$env:ARCHIVE_DB=Join-Path $state 'archive.sqlite'
$env:ARCHIVE_SETTINGS=$settingsPath
$env:ARCHIVE_LISTEN_HOST='127.0.0.1'
try { & $python (Join-Path $projectRoot 'start.py') }
finally { Remove-Item Env:ARCHIVE_TOKEN -ErrorAction SilentlyContinue }
