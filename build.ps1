param([string]$Python = "")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot/setup.ps1" -Build -Python $Python
& ".venv-hamstercam/Scripts/python.exe" -m PyInstaller --noconfirm HamsterCam.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
Copy-Item -LiteralPath "README.md" -Destination "dist/HamsterCam/README.md" -Force
Write-Host "Executable: dist\HamsterCam\HamsterCam.exe"
