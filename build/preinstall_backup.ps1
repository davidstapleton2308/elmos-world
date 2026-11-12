param(
  [Parameter(Mandatory=$true)][string]$AppDir
)
$ErrorActionPreference = 'Stop'
$backupRoot = Join-Path $env:LOCALAPPDATA 'ElmosWorldRollback'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
$dest = Join-Path $backupRoot ($stamp + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $dest -Force | Out-Null
function BackupFolder([string]$source,[string]$targetName) {
  if (-not (Test-Path -LiteralPath $source -PathType Container)) { return }
  $target = Join-Path $dest $targetName
  New-Item -ItemType Directory -Path $target -Force | Out-Null
  & robocopy.exe $source $target /E /XJ /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Backup copy failed for $source (robocopy $LASTEXITCODE)." }
}
try {
  BackupFolder $AppDir 'program'
  BackupFolder (Join-Path $env:LOCALAPPDATA 'SteamMatch') 'SteamMatch'
  BackupFolder (Join-Path $env:LOCALAPPDATA 'ElmosWorld') 'ElmosWorld'
  BackupFolder (Join-Path $env:LOCALAPPDATA 'ElmosControllerLab') 'ElmosControllerLab'
  $manifest = @{
    date = (Get-Date).ToString('o')
    originalAppDir = $AppDir
    snapshot = $dest
    program = (Test-Path -LiteralPath (Join-Path $dest 'program\ElmosWorld.exe'))
  }
  $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dest 'backup-manifest.json') -Encoding UTF8
  if (Test-Path -LiteralPath (Join-Path $dest 'program\ElmosWorld.exe')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'restore_previous.ps1') -Destination (Join-Path $dest 'restore_previous.ps1') -Force
    Set-Content -LiteralPath (Join-Path $dest 'RESTORE_PREVIOUS_VERSION.bat') -Value '@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restore_previous.ps1"
pause' -Encoding ASCII
  }
  Write-Output "Previous version backed up to: $dest"
  exit 0
} catch {
  Write-Error ("Update stopped: could not safely back up your existing Elmos World. " + $_.Exception.Message)
  exit 1
}
