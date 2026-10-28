param([string]$OutputDirectory)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $projectRoot 'build\windows' }
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\vbc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw '.NET Framework VB compiler not found.' }
$executable=Join-Path $OutputDirectory 'ArchiveSearch.exe'
& $compiler /nologo /target:winexe "/out:$executable" "/win32icon:$(Join-Path $projectRoot 'assets\ArchiveSearch.ico')" /reference:System.dll,System.Core.dll,System.Drawing.dll,System.Windows.Forms.dll,System.Net.Http.dll,System.Web.Extensions.dll,System.Security.dll (Join-Path $projectRoot 'ArchiveSearch.vb') (Join-Path $projectRoot 'SettingsWindow.vb')
if ($LASTEXITCODE -ne 0) { throw 'Windows compilation failed.' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'assets\ArchiveSearch.ico') -Destination $OutputDirectory
Write-Output "Built $executable"
