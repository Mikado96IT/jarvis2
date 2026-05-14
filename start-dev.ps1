$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$py313 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
$venv = ".venv313"

if (Test-Path $py313) {
    if (-not (Test-Path "$venv\Scripts\python.exe")) {
        & $py313 -m venv $venv
    }
    & "$venv\Scripts\python.exe" -m pip install -r requirements.txt
    & "$venv\Scripts\python.exe" server.py
    exit
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
