param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][int]$ParentId,
  [Parameter(Mandatory=$true)][string]$AppExe,
  [Parameter(Mandatory=$true)][string]$LogPath,
  [Parameter(Mandatory=$true)][string]$StatusPath
)
$ErrorActionPreference = 'Stop'

function Write-UpdateLog([string]$Message) {
  $line = ('{0:u} {1}' -f (Get-Date), $Message)
  Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}
function Set-UpdateState([string]$State, [string]$Detail) {
  @{ state=$State; detail=$Detail; time=(Get-Date).ToString('o') } |
    ConvertTo-Json -Compress |
    Set-Content -LiteralPath $StatusPath -Encoding UTF8
}
function Restart-InstalledApp {
  if (Test-Path -LiteralPath $AppExe -PathType Leaf) {
    try {
      Start-Process -FilePath $AppExe | Out-Null
      Write-UpdateLog 'Relaunch requested.'
    } catch {
      Write-UpdateLog ('Relaunch failed: ' + $_.Exception.Message)
    }
  }
}
try {
  New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
  Write-UpdateLog ('Update worker launched. Parent PID ' + $ParentId)
  Set-UpdateState 'waiting' 'Waiting for Elmos World to exit'
  $deadline = (Get-Date).AddSeconds(120)
  while ($true) {
    $parent = Get-Process -Id $ParentId -ErrorAction SilentlyContinue
    # IMPORTANT: Already-exited parent is normal. The previous worker
    # aborted with exit 3 here and the application remained closed.
    if ($null -eq $parent) { break }
    if ((Get-Date) -ge $deadline) { throw 'Elmos World did not exit within 120 seconds' }
    Start-Sleep -Milliseconds 300
  }
  Start-Sleep -Milliseconds 600
  Write-UpdateLog 'App closed; starting installer'
  if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) { throw 'Verified installer file is missing' }
  Set-UpdateState 'installing' 'Installing the verified update'
  $installLog = Join-Path (Split-Path -Parent $Installer) 'installer.log'
  $args = @('/SILENT','/NORESTART','/CLOSEAPPLICATIONS',('/LOG="' + $installLog + '"'))
  $process = Start-Process -FilePath $Installer -ArgumentList $args -Wait -PassThru
  $code = [int]$process.ExitCode
  Write-UpdateLog ("Installer finished with exit code $code")
  if ($code -ne 0) { throw "Installer failed ($code). See $installLog" }
  Set-UpdateState 'complete' 'Update installed and app restarted'
  Restart-InstalledApp
  Write-UpdateLog 'Update worker finished normally'
  exit 0
}
catch {
  $detail = $_.Exception.Message
  try {
    Write-UpdateLog ("UPDATE FAILED: $detail")
    Set-UpdateState 'failed' $detail
    Restart-InstalledApp
  } catch {}
  exit 1
}
