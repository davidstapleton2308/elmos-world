# Prepare the pinned, redistributable Elmos Input runtime for Windows builds.
# The archive includes DS4Windows 5 and its matching VIIPER backend; it is NOT
# installed, run, or elevated on the build machine.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'build\vendor\ElmosInput'
$staging = Join-Path $root 'build\vendor\ElmosInput.staging'
$archive = Join-Path $root 'build\vendor\DS4Windows_VIIPER_x64.zip'
$uri = 'https://github.com/hbashton/DS4Windows/releases/download/VIIPERRC4.6.6/DS4Windows_VIIPER_x64.zip'
$expected = 'b97daa4c605c778afaa64fcc8283e2218597a1b8bcf6b55cd2443302346ba4af'
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
    # Keep upstream notices/licenses, and bundle matching source archives.
    $manifest = @'
{
  "name": "Elmos Input bundled compatibility runtime",
  "upstream": "hbashton/DS4Windows",
  "release": "VIIPERRC4.6.6",
  "asset": "DS4Windows_VIIPER_x64.zip",
  "sha256": "b97daa4c605c778afaa64fcc8283e2218597a1b8bcf6b55cd2443302346ba4af",
  "license_note": "GPL-covered third party components. Upstream notices and matching source archives are included in CorrespondingSource."
}
'@
    Set-Content -LiteralPath (Join-Path $staging 'ELMOS_INPUT_MANIFEST.json') -Value $manifest -Encoding utf8
    # Redistribute the corresponding GPL source alongside the binary.
    $sources = @(
        @{ Name='DS4Windows-VIIPERRC4.6.6-SOURCE.zip'; Sha='c37edfa17a82ce765a84064ef6900196e11354a12b11b568b79e78c0b5264003' },
        @{ Name='VIIPER-0.1.9-rc4.6.6-SOURCE.zip'; Sha='fbdf251480a8a2aef5f3c5bae7f4ef288afb3cd26a3a4aa60d1f491a301ef655' }
    )
    $sourceDir = Join-Path $staging 'CorrespondingSource'
    New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null
    foreach ($source in $sources) {
        $sourceUri = 'https://github.com/hbashton/DS4Windows/releases/download/VIIPERRC4.6.6/' + $source.Name
        $sourceFile = Join-Path $sourceDir $source.Name
        Invoke-WebRequest -Uri $sourceUri -OutFile $sourceFile -MaximumRedirection 10
        $sourceHash = (Get-FileHash $sourceFile -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sourceHash -ne $source.Sha) { throw "Corresponding source checksum mismatch: $($source.Name)" }
    }
        Move-Item $staging $target
    Write-Host 'Verified Elmos Input runtime staged into the Windows build.'
} finally {
    if (Test-Path $archive) { Remove-Item $archive -Force }
    if (Test-Path $staging) { Remove-Item $staging -Force -Recurse }
}
