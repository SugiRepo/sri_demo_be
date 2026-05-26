# Dev server with app logging to terminal + logs/app.log
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

& .\venv\Scripts\Activate.ps1
$env:PYTHONUNBUFFERED = "1"

python -m uvicorn main:app --reload --log-level info
