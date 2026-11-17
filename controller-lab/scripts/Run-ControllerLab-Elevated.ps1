param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$LabArgs
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root 'bridge/publish/Elmos.ControllerLab.Bridge.exe'
if (!(Test-Path $Exe)) { throw 'Run Build-ControllerLab.ps1 before starting the elevated lab.' }
$Python = (Get-Command python -ErrorAction Stop).Source
& $Python -m pip install -e $Root
if ($LASTEXITCODE -ne 0) { throw 'Controller Lab Python package setup failed.' }
$Arguments = @('-m', 'elmos_controller_lab.lab', '--bridge', $Exe) + $LabArgs
$argLine = ($Arguments | ForEach-Object { '"' + ($_ -replace '"','""') + '"' }) -join ' '
$Current = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$IsAdmin = $Current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
    Write-Host 'The virtual-device bridge needs administrator rights to create Windows virtual controllers.' -ForegroundColor Yellow
    Write-Host 'Approve the Windows UAC prompt to continue. No driver is installed by this launch script.' -ForegroundColor Yellow
    $process = Start-Process -FilePath $Python -ArgumentList $argLine -WorkingDirectory $Root -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
}
& $Python @Arguments
exit $LASTEXITCODE
