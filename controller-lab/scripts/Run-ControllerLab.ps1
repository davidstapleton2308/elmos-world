$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency setup failed.' }
    python -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw 'Controller Lab package setup failed.' }
    python -m elmos_controller_lab.lab @args
    exit $LASTEXITCODE
}
finally { Pop-Location }
