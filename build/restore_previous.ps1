$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $root 'backup-manifest.json') -Raw | ConvertFrom-Json
$target = [string]$manifest.originalAppDir
if (-not (Test-Path -LiteralPath (Join-Path $root 'program\ElmosWorld.exe') -PathType Leaf)) {
  throw 'No previous executable found in this backup.'
}
if (Get-Process -Name ElmosWorld -ErrorAction SilentlyContinue) {
  throw 'Close Elmos World first, then run RESTORE_PREVIOUS_VERSION.bat again.'
}
function RestoreFolder([string]$name,[string]$destination) {
  $src = Join-Path $root $name
  if (-not (Test-Path -LiteralPath $src -PathType Container)) { return }
  New-Item -ItemType Directory -Path $destination -Force | Out-Null
  & robocopy.exe $src $destination /E /XJ /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Could not restore $name ($LASTEXITCODE)." }
}
RestoreFolder 'program' $target
RestoreFolder 'SteamMatch' (Join-Path $env:LOCALAPPDATA 'SteamMatch')
RestoreFolder 'ElmosWorld' (Join-Path $env:LOCALAPPDATA 'ElmosWorld')
RestoreFolder 'ElmosControllerLab' (Join-Path $env:LOCALAPPDATA 'ElmosControllerLab')
Write-Host 'Restored the saved previous Elmos World application and settings.' -ForegroundColor Green
Start-Process -FilePath (Join-Path $target 'ElmosWorld.exe')
