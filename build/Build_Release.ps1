# Elmos World 3.1.1 desktop builder - robust Python detection for Windows PowerShell 5.1.
# Runs only inside the extracted build kit. Does not change the existing C:\Gaming installation.
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $Root
Write-Host ''
Write-Host 'ELMOS WORLD 3.1.1 - WINDOWS DESKTOP APP BUILDER' -ForegroundColor Cyan
Write-Host 'Builds a standalone ElmosWorld.exe and an optional Windows Setup installer.'
Write-Host 'Build requirement: Windows 10/11 x64 + Python 3.11, 3.12 or 3.13 (64-bit).'
Write-Host ''

function Test-PythonRuntime {
  param([string] $Exe, [string] $Prefix = '')
  # A process probe avoids PowerShell 5.1's NativeCommandError when `py -3.12`
  # is missing. It also rejects the Microsoft Store python.exe placeholder.
  if ([string]::IsNullOrWhiteSpace($Exe)) { return $null }
  $ArgString = (($Prefix.Trim() + ' -c ' + '"import sys,struct;print(''EW_RUNTIME:''+str(sys.version_info[0])+''.''+str(sys.version_info[1])+'':''+str(struct.calcsize(''P'')*8))"').Trim())
  $info = New-Object System.Diagnostics.ProcessStartInfo
  $info.FileName = $Exe
  $info.Arguments = $ArgString
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $info
  try {
    if (-not $proc.Start()) { return $null }
    $output = $proc.StandardOutput.ReadToEnd()
    # Python produces a single short error message if it can't start.
    $null = $proc.StandardError.ReadToEnd()
    if (-not $proc.WaitForExit(15000)) {
      try { $proc.Kill() } catch {}
      return $null
    }
    if ($proc.ExitCode -ne 0) { return $null }
    if ($output -match 'EW_RUNTIME:3\.(11|12|13):64') {
      return [pscustomobject]@{ Exe = $Exe; Prefix = $Prefix; Version = ('3.' + $Matches[1]) }
    }
  } catch { return $null }
  finally { $proc.Dispose() }
  return $null
}

function Find-PythonRuntime {
  $commands = @()
  $py = Get-Command 'py.exe' -CommandType Application -ErrorAction SilentlyContinue
  if ($py) {
    # First preference: Python 3.12. Accept other supported x64 runtimes.
    foreach ($version in @('3.12', '3.13', '3.11')) {
      $commands += [pscustomobject]@{ Exe = $py.Source; Prefix = ('-' + $version) }
    }
  }
  foreach ($name in @('python.exe', 'python3.exe')) {
    $found = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
    if ($found) { $commands += [pscustomobject]@{ Exe = $found.Source; Prefix = '' } }
  }
  # Some Windows Python installations are registered but not on PATH.
  foreach ($version in @('312', '313', '311')) {
    foreach ($folder in @(
      (Join-Path $env:LOCALAPPDATA ('Programs\Python\Python' + $version)),
      (Join-Path $env:ProgramFiles ('Python' + $version))
    )) {
      $candidate = Join-Path $folder 'python.exe'
      if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $commands += [pscustomobject]@{ Exe = $candidate; Prefix = '' }
      }
    }
  }
  foreach ($candidate in $commands) {
    $result = Test-PythonRuntime -Exe $candidate.Exe -Prefix $candidate.Prefix
    if ($result) { return $result }
  }
  return $null
}

$Python = Find-PythonRuntime
if (-not $Python) {
  Write-Host 'No supported 64-bit Python was found.' -ForegroundColor Yellow
  Write-Host 'Elmos World itself will not need Python after this build.'
  $Winget = Get-Command 'winget.exe' -CommandType Application -ErrorAction SilentlyContinue
  if ($Winget) {
    Write-Host ''
    $answer = Read-Host 'Install official Python 3.12 using Windows Package Manager now? [Y/N]'
    if ($answer -match '^(y|yes)$') {
      Write-Host 'Installing Python 3.12 for BUILDING only...' -ForegroundColor Cyan
      $previous = $ErrorActionPreference
      $ErrorActionPreference = 'Continue'
      try {
        & $Winget.Source install --exact --id Python.Python.3.12 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Write-Warning ('Python installation returned code ' + $LASTEXITCODE) }
      } catch { Write-Warning ('winget could not install Python: ' + $_.Exception.Message) }
      finally { $ErrorActionPreference = $previous }
      $Python = Find-PythonRuntime
    }
  }
  if (-not $Python) {
    Write-Host ''
    Write-Host 'Python was not installed or Windows has not registered it yet.' -ForegroundColor Yellow
    Write-Host 'Install Python 3.12 x64 from https://www.python.org/downloads/windows/'
    Write-Host 'Close and reopen the build window, then run INSTALL_APP.bat again.'
    exit 2
  }
}
Write-Host ('Using Python ' + $Python.Version + ' (64-bit): ' + $Python.Exe) -ForegroundColor Green

$Venv = Join-Path $Root '.buildvenv'
$BuildPython = Join-Path $Venv 'Scripts\python.exe'
if (Test-Path -LiteralPath $BuildPython -PathType Leaf) {
  $existing = Test-PythonRuntime -Exe $BuildPython
  if ((-not $existing) -or ($existing.Version -ne $Python.Version)) {
    Write-Host 'Recreating an incompatible/incomplete build environment...'
    Remove-Item -LiteralPath $Venv -Recurse -Force
  }
}
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
  Write-Host 'Creating an isolated build environment...'
  if ($Python.Prefix) {
    & $Python.Exe $Python.Prefix -m venv $Venv
  } else {
    & $Python.Exe -m venv $Venv
  }
  if ($LASTEXITCODE -ne 0) { throw 'Python could not create the build environment.' }
}
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
  throw 'The isolated Python environment did not create its python.exe.'
}

Write-Host 'Installing build dependencies...'
& $BuildPython -m pip install --disable-pip-version-check -r (Join-Path $Root 'build\requirements-windows.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python package installation failed. Check the output above.' }

Write-Host 'Compiling ElmosWorld.exe...' -ForegroundColor Cyan
& $BuildPython -m PyInstaller --noconfirm --clean `
  --distpath (Join-Path $Root 'dist') `
  --workpath (Join-Path $Root 'build\work') `
  (Join-Path $Root 'build\ElmosWorld.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed. See its output above.' }
$Exe = Join-Path $Root 'dist\ElmosWorld\ElmosWorld.exe'
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw 'ElmosWorld.exe was not produced.' }
Write-Host ('EXE built: ' + $Exe) -ForegroundColor Green

Write-Host 'Building standalone Elmos Controller runtime...'
& $BuildPython -m PyInstaller --noconfirm --clean --distpath (Join-Path $Root 'dist\\controller-runtime') --workpath (Join-Path $Root 'build\\controller-runtime-work') (Join-Path $Root 'build\\ControllerRuntime.spec')
if ($LASTEXITCODE -ne 0) { throw 'Controller runtime helper build failed.' }
$Bundle = Join-Path $Root 'dist\\ElmosWorld'
$Internal = Join-Path $Bundle '_internal'
if (-not (Test-Path -LiteralPath $Internal)) { $Internal = $Bundle }
$RuntimeDir = Join-Path $Internal 'controller-runtime'
$BridgeDir = Join-Path $Internal 'controller-lab\\bridge\\publish'
New-Item -ItemType Directory -Force -Path $RuntimeDir,$BridgeDir | Out-Null
Copy-Item (Join-Path $Root 'dist\\controller-runtime\\ElmosControllerRuntime.exe') $RuntimeDir -Force
Copy-Item (Join-Path $Root 'controller-lab\\bridge\\publish\\Elmos.ControllerLab.Bridge.exe') $BridgeDir -Force
$NoticeDir = Join-Path $Internal 'controller-lab'
New-Item -ItemType Directory -Force -Path $NoticeDir | Out-Null
foreach ($name in @('LICENSE','THIRD-PARTY-NOTICES.txt')) {
  $source = Join-Path $Root ('controller-lab\\runtime\\' + $name)
  if (Test-Path -LiteralPath $source) { Copy-Item $source $NoticeDir -Force }
}

# Verify that required runtime assets were actually bundled before packaging.
Write-Host 'Checking standalone application dependencies...' -ForegroundColor Cyan
$SelfTest = Start-Process -FilePath $Exe -ArgumentList '--self-test' -Wait -PassThru
if ($SelfTest.ExitCode -ne 0) {
  Write-Host 'Standalone self-test failed. Check:' -ForegroundColor Red
  Write-Host ('  ' + (Join-Path $env:LOCALAPPDATA 'ElmosWorld\logs\launcher.log'))
  throw 'ElmosWorld.exe is present but did not pass its startup dependency check.'
}

function Find-InnoCompiler {
  $candidatePaths = @()
  $folders = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)
  foreach ($base in $folders) {
    if (-not $base) { continue }
    foreach ($version in @('6', '7')) {
      $candidatePaths += Join-Path $base ('Inno Setup ' + $version + '\ISCC.exe')
      if ($base -eq $env:LOCALAPPDATA) {
        $candidatePaths += Join-Path $base ('Programs\Inno Setup ' + $version + '\ISCC.exe')
      }
    }
  }
  $iscc = Get-Command 'ISCC.exe' -CommandType Application -ErrorAction SilentlyContinue
  if ($iscc) { $candidatePaths += $iscc.Source }
  foreach ($candidate in $candidatePaths) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
  }
  return $null
}

$Compiler = Find-InnoCompiler
if (-not $Compiler) {
  Write-Host 'Inno Setup is missing. Attempting Windows Package Manager install...'
  $Winget = Get-Command 'winget.exe' -CommandType Application -ErrorAction SilentlyContinue
  if ($Winget) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      & $Winget.Source install --exact --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements
      if ($LASTEXITCODE -ne 0) { Write-Warning ('Inno Setup installation returned code ' + $LASTEXITCODE) }
    } catch { Write-Warning ('winget failed to install Inno Setup: ' + $_.Exception.Message) }
    finally { $ErrorActionPreference = $previous }
    $Compiler = Find-InnoCompiler
  }
}
if (-not $Compiler) {
  Write-Host ''
  Write-Host 'The portable ElmosWorld.exe is BUILT and validated.' -ForegroundColor Green
  Write-Host ('You can run it from: ' + $Exe)
  Write-Host 'For a Windows Setup installer, install Inno Setup 6 or newer:' -ForegroundColor Yellow
  Write-Host '  https://jrsoftware.org/isdl.php'
  Write-Host 'Then run INSTALL_APP.bat again. The built EXE is preserved.'
  exit 3
}

Write-Host ('Building Windows Setup using: ' + $Compiler) -ForegroundColor Cyan
& $Compiler (Join-Path $Root 'build\ElmosWorld.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compiler failed.' }
$Setup = Join-Path $Root 'dist_setup\ElmosWorld_Setup_3.1.1.exe'
if (-not (Test-Path -LiteralPath $Setup -PathType Leaf)) { throw 'Setup installer not found after compilation.' }
Write-Host ('SUCCESS: ' + $Setup) -ForegroundColor Green
