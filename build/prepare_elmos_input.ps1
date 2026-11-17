# Prepare the pinned, redistributable Elmos Input runtime for Windows builds.
# The archive includes DS4Windows 5 and its matching VIIPER backend; it is NOT
# installed, run, or elevated on the build machine.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'build\vendor\ElmosInput'
$staging = Join-Path $root 'build\vendor\ElmosInput.staging'
$archive = Join-Path $root 'build\vendor\DS4Windows_VIIPER_x64.zip'
$uri = 'https://github.com/hbashton/DS4Windows/releases/download/VIIPERRC4.6.7/DS4Windows_VIIPER_x64.zip'
$expected = '925200002ec319dea8c3fa9eabf66462749d42774399110f62fa48a5d828aa1f'
New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
if (Test-Path $target) {
    $exe = @(Get-ChildItem $target -Filter DS4Windows.exe -Recurse -File)
    if ($exe.Count -eq 1) {
        Write-Host 'Elmos Input bundle already staged; preserving it.'
        exit 0
    }
    throw 'Existing Elmos Input bundle is incomplete. Remove it manually before retrying.'
}
try {
    Invoke-WebRequest -Uri $uri -OutFile $archive -MaximumRedirection 10
    $actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw 'Controller runtime checksum mismatch; refusing archive.' }
    if (Test-Path $staging) { throw 'Staging folder already exists; refusing overwrite.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $staging
    $exes = @(Get-ChildItem $staging -Filter DS4Windows.exe -Recurse -File)
    if ($exes.Count -ne 1) { throw 'Controller bundle must contain exactly one DS4Windows.exe.' }
    # Keep upstream notices/licenses inside the bundle. The release must also
    # preserve access to the matching GPL source and VIIPER source distributions.
    $manifest = @'
{
  "name": "Elmos Input bundled compatibility runtime",
  "upstream": "hbashton/DS4Windows",
  "release": "VIIPERRC4.6.7",
  "asset": "DS4Windows_VIIPER_x64.zip",
  "sha256": "925200002ec319dea8c3fa9eabf66462749d42774399110f62fa48a5d828aa1f",
  "license_note": "GPL-covered third party components. Preserve upstream notices and supply corresponding source on distribution."
}
'@
    Set-Content -LiteralPath (Join-Path $staging 'ELMOS_INPUT_MANIFEST.json') -Value $manifest -Encoding utf8
    Move-Item $staging $target
    Write-Host 'Verified Elmos Input runtime staged into the Windows build.'
} finally {
    if (Test-Path $archive) { Remove-Item $archive -Force }
    if (Test-Path $staging) { Remove-Item $staging -Force -Recurse }
}
