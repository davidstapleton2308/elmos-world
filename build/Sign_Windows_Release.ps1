# Elmos World Authenticode signing; requires trusted code-signing certificate
# with private key already installed in CurrentUser\My, and Windows SDK SignTool.
# Does NOT import or export keys or alter Windows security settings.
param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$Thumbprint)
$ErrorActionPreference='Stop'
$Root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Thumbprint=$Thumbprint.ToUpperInvariant()
$cert=Get-Item -LiteralPath ('Cert:\CurrentUser\My\'+$Thumbprint) -ErrorAction Stop
if (-not $cert.HasPrivateKey) { throw 'Selected signing certificate has no accessible private key.' }
if ($cert.NotAfter -le (Get-Date)) { throw 'Signing certificate is expired.' }
$eku=@($cert.EnhancedKeyUsageList | ForEach-Object {$_.ObjectId})
if ($eku -notcontains '1.3.6.1.5.5.7.3.3') { throw 'Certificate lacks Code Signing EKU.' }
$chain=New-Object System.Security.Cryptography.X509Certificates.X509Chain
if (-not $chain.Build($cert)) {
  throw ('Certificate is not trusted by Windows: '+(($chain.ChainStatus | ForEach-Object {$_.StatusInformation.Trim()}) -join '; '))
}
$signTool=Get-Command signtool.exe -CommandType Application -ErrorAction SilentlyContinue
if ($signTool) { $signtoolPath=$signTool.Source }
else {
  $kit=Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Windows Kits\10\bin'
  $signtoolPath=Get-ChildItem -LiteralPath $kit -Recurse -Filter 'signtool.exe' -File -ErrorAction SilentlyContinue |
    Where-Object {$_.FullName -match '\\x64\\signtool\.exe$'} |
    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $signtoolPath) { throw 'Install Windows SDK SignTool first.' }
$dist=Join-Path $Root 'dist\ElmosWorld'
if (-not (Test-Path -LiteralPath (Join-Path $dist 'ElmosWorld.exe'))) { throw 'Build ElmosWorld.exe before signing.' }
$files=Get-ChildItem -LiteralPath $dist -Recurse -File | Where-Object {$_.Extension -in @('.exe','.dll','.pyd')}
Write-Host ('Signing '+$files.Count+' executable binaries with certificate '+$Thumbprint)
foreach ($file in $files) {
  & $signtoolPath sign /sha1 $Thumbprint /s My /fd SHA256 /tr 'http://timestamp.acs.microsoft.com' /td SHA256 $file.FullName
  if ($LASTEXITCODE -ne 0) { throw ('Failed to sign '+$file.FullName) }
  & $signtoolPath verify /pa $file.FullName
  if ($LASTEXITCODE -ne 0) { throw ('Failed to verify '+$file.FullName) }
}
$compiler=Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Inno Setup 6 not found.' }
# Inno signs the outer setup, temporary extracted .tmp engine, and uninstaller.
# Post-signing setup.exe alone is NOT sufficient.
$command='"'+$signtoolPath+'" sign /sha1 '+$Thumbprint+' /s My /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 $f'
& $compiler ('/Selmos='+$command) '/DELMOS_SIGNED' (Join-Path $Root 'build\ElmosWorld.iss')
if ($LASTEXITCODE -ne 0) { throw 'Signed Inno setup build failed.' }
$manifest=Get-Content (Join-Path $Root 'release_manifest.json') -Raw | ConvertFrom-Json
$installer=Join-Path $Root ('dist_setup\ElmosWorld_Setup_'+$manifest.version+'.exe')
if (-not (Test-Path -LiteralPath $installer)) { throw 'Signed installer missing.' }
& $signtoolPath verify /pa $installer
if ($LASTEXITCODE -ne 0) { throw 'Installer Authenticode signature validation failed.' }
Write-Host ('SIGNED & VERIFIED: '+$installer) -ForegroundColor Green
Write-Host 'Smart App Control compatibility must still be tested on the destination device.'
