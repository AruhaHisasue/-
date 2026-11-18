$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name IndividualSupportPlan --paths src --add-data "templates;templates" --add-data "mappings;mappings" --add-data "resources/r806_fee_master_fixed.zip;resources" app.py
if ($LASTEXITCODE -ne 0) { throw 'ビルドに失敗しました' }
