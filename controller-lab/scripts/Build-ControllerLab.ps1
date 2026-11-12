$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$RuntimeDll = Join-Path $Root 'runtime/HIDMaestro.Core.dll'
if (!(Test-Path $RuntimeDll)) {
    & (Join-Path $PSScriptRoot 'Setup-ControllerLab.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'SDK setup failed.' }
}
$Project = Join-Path $Root 'bridge/Elmos.ControllerLab.Bridge.csproj'
$Output = Join-Path $Root 'bridge/publish'
dotnet publish $Project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $Output
if ($LASTEXITCODE -ne 0) { throw 'Controller Lab bridge build failed.' }
$Exe = Join-Path $Output 'Elmos.ControllerLab.Bridge.exe'
if (!(Test-Path $Exe)) { throw 'The published bridge executable is missing.' }
foreach ($notice in @('LICENSE','THIRD-PARTY-NOTICES.txt')) {
    $source = Join-Path $Root ("runtime/" + $notice)
    if (Test-Path $source) { Copy-Item $source $Output -Force }
}
& $Exe --catalog-check
if ($LASTEXITCODE -ne 0) { throw 'The virtual-controller profile catalog failed its startup check.' }
Write-Host "Build complete: $Exe" -ForegroundColor Green
