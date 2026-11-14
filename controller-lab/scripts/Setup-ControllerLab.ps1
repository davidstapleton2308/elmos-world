$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root 'runtime'
$Cache = Join-Path $Root '.cache'
$Version = '2.1.0'
$Url = "https://github.com/hifihedgehog/HIDMaestro/releases/download/v$Version/HIDMaestro-v$Version.zip"
$ExpectedSha256 = '7FE349F163864B8DFC36117AF260D51BAC94A2263B6CDFA719CB364A808397B4'
New-Item -ItemType Directory -Force -Path $Runtime, $Cache | Out-Null
$Zip = Join-Path $Cache "HIDMaestro-v$Version.zip"
$Extract = Join-Path $Cache "HIDMaestro-v$Version"
if (!(Test-Path $Zip)) {
    Write-Host "Downloading the pinned HIDMaestro $Version SDK..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $Zip
}
$ActualSha256 = (Get-FileHash -Path $Zip -Algorithm SHA256).Hash.ToUpperInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    Remove-Item -Force $Zip
    throw "HIDMaestro archive checksum mismatch. Expected $ExpectedSha256, got $ActualSha256."
}
if (!(Test-Path $Extract)) { Expand-Archive -Path $Zip -DestinationPath $Extract -Force }
$Sdk = Get-ChildItem -Path $Extract -Filter 'HIDMaestro.Core.dll' -File -Recurse | Select-Object -First 1
if (!$Sdk) { throw 'The verified SDK archive did not contain HIDMaestro.Core.dll.' }
Copy-Item -Path $Sdk.FullName -Destination (Join-Path $Runtime 'HIDMaestro.Core.dll') -Force
foreach ($name in @('LICENSE', 'THIRD-PARTY-NOTICES.txt')) {
    $notice = Get-ChildItem -Path $Extract -Filter $name -File -Recurse | Select-Object -First 1
    if ($notice) { Copy-Item $notice.FullName (Join-Path $Runtime $name) -Force }
}
Write-Host 'HIDMaestro SDK downloaded, checksum-verified and staged.' -ForegroundColor Green
Write-Host 'No driver, certificate, device or Windows setting was installed or changed.' -ForegroundColor Yellow
