$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$credentialFile = Get-Content '.local/db.json' | ConvertFrom-Json
$testPort = if ($env:RAILSYNC_TEST_PORT) { [int]$env:RAILSYNC_TEST_PORT } else { 55432 }
$env:RAILSYNC_DATABASE_URL = 'postgresql+psycopg://railsync:' + $credentialFile.password + '@127.0.0.1:' + $testPort + '/railsync_test'
$env:PYTHONPATH = 'backend'
& '.venv/Scripts/python.exe' -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& '.venv/Scripts/python.exe' -m pytest @args
exit $LASTEXITCODE
