$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$output=Join-Path $projectRoot 'build\oauth-tests.exe'
New-Item -ItemType Directory -Force (Split-Path $output -Parent) | Out-Null
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\vbc.exe'
& $compiler /nologo /target:exe "/out:$output" /reference:System.dll,System.Core.dll,System.Net.Http.dll,System.Web.dll (Join-Path $projectRoot 'GoogleDriveLogin.vb') (Join-Path $projectRoot 'tests\GoogleDriveLoginTests.vb')
if ($LASTEXITCODE -ne 0) { throw 'OAuth test compilation failed.' }
& $output
if ($LASTEXITCODE -ne 0) { throw 'OAuth callback checks failed.' }
