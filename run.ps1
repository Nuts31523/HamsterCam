$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$appPython = Join-Path $PSScriptRoot ".venv-hamstercam/Scripts/python.exe"
if (!(Test-Path -LiteralPath $appPython)) { throw "Run setup.ps1 first." }
& $appPython main.py
exit $LASTEXITCODE
