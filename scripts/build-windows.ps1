param([switch]$SkipTests, [string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
$studioOutput = [IO.Path]::GetFullPath((Join-Path $studioRoot $OutputDirectory))
if (-not $studioOutput.StartsWith($studioRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build output must be a folder inside this checkout.' }
if (-not (Test-Path -LiteralPath $studioPython)) { throw 'Create .venv and install .[dev] first.' }
Push-Location $studioRoot
try {
    if (-not $SkipTests) {
        & $studioPython -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    }
    & $studioPython scripts/make_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon build failed.' }
    & $studioPython -m PyInstaller --noconfirm --clean --distpath $studioOutput VegaBridgeStudio.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    $smokeProcess = Start-Process -FilePath (Join-Path $studioOutput 'VegaBridgeStudio\VegaBridgeStudio.exe') -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $smokeProcess.WaitForExit(20000)) { Stop-Process -Id $smokeProcess.Id; throw 'Packaged executable did not finish its smoke test.' }
    if ($smokeProcess.ExitCode -ne 0) { throw 'Packaged executable smoke test failed.' }
    & $studioPython scripts/package_review.py $studioOutput
    if ($LASTEXITCODE -ne 0) { throw 'Review packaging failed.' }
} finally { Pop-Location }
