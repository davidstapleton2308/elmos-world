$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root 'bridge/publish/Elmos.ControllerLab.Bridge.exe'
if (!(Test-Path $Exe)) { throw 'Run Build-ControllerLab.ps1 before installing the driver.' }
$Python = (Get-Command python -ErrorAction Stop).Source
& $Python -m pip install -e $Root
if ($LASTEXITCODE -ne 0) { throw 'Controller Lab Python package setup failed.' }
$Arguments = @('-m', 'elmos_controller_lab.lab', '--bridge', $Exe, 'install-driver')
$Current = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$IsAdmin = $Current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$IsAdmin) {
    Write-Host 'Windows will ask for administrator approval to install the virtual-controller driver and its local signing certificate.' -ForegroundColor Yellow
    Write-Host 'Nothing is installed unless you approve the UAC prompt.' -ForegroundColor Yellow
    $argLine = ($Arguments | ForEach-Object { '"' + ($_ -replace '"','""') + '"' }) -join ' '
    $process = Start-Process -FilePath $Python -ArgumentList $argLine -WorkingDirectory $Root -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
}
& $Python @Arguments
exit $LASTEXITCODE
