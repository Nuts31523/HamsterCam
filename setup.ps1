param(
    [string]$Python = "",
    [switch]$Build
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot ".venv-hamstercam/Scripts/python.exe"
$check = "import struct, sys; assert sys.version_info[:2] in ((3, 11), (3, 12)) and struct.calcsize('P') == 8, 'CPython 3.11 or 3.12 x64 required'"

if (!(Test-Path -LiteralPath $venvPython)) {
    if ($Python) {
        & $Python -c $check
        if ($LASTEXITCODE -ne 0) { throw "Use -Python with a CPython 3.11 or 3.12 x64 executable." }
        & $Python -m venv .venv-hamstercam
    }
    else {
        if (!(Get-Command py -ErrorAction SilentlyContinue)) {
            throw "Install CPython 3.12 x64 from python.org or pass its executable using -Python."
        }
        & py -3.12-64 -c $check
        if ($LASTEXITCODE -eq 0) {
            & py -3.12-64 -m venv .venv-hamstercam
        }
        else {
            & py -3.11-64 -c $check
            if ($LASTEXITCODE -ne 0) { throw "Install CPython 3.12 x64 from python.org." }
            & py -3.11-64 -m venv .venv-hamstercam
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}

& $venvPython -c $check
if ($LASTEXITCODE -ne 0) { throw "The .venv-hamstercam environment needs CPython 3.11 or 3.12 x64." }
$requirements = if ($Build) { "requirements-build.txt" } else { "requirements.txt" }
& $venvPython -m pip --disable-pip-version-check install -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& $venvPython tools/get_model.py
if ($LASTEXITCODE -ne 0) { throw "Face Landmarker model is unavailable." }
Write-Host "HamsterCam is ready. Run .\run.ps1"
