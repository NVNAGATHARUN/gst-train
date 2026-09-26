param(
    [Parameter(Mandatory=$true)][string]$BackupFile
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$backup = (Resolve-Path -LiteralPath $BackupFile).Path
$hashFile = "$backup.sha256"
if (-not (Test-Path -LiteralPath $hashFile)) { throw "Missing checksum file: $hashFile" }
$expected = ((Get-Content -LiteralPath $hashFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw 'Backup SHA256 mismatch; restore refused' }

Push-Location $projectRoot
try {
    & docker compose --profile recovery up -d restore-db
    if ($LASTEXITCODE -ne 0) { throw 'Could not start isolated restore database' }
    $ready = $false
    foreach ($attempt in 1..30) {
        & docker compose --profile recovery exec -T restore-db pg_isready --username=railsync_restore --dbname=railsync_restore *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Isolated restore database did not become ready' }
    $tableCount = & docker compose --profile recovery exec -T restore-db psql --username=railsync_restore --dbname=railsync_restore --tuples-only --no-align --command="SELECT count(*) FROM pg_tables WHERE schemaname='public';"
    if ($LASTEXITCODE -ne 0 -or [int]$tableCount -ne 0) {
        throw 'Restore target is not empty; refusing to overwrite it'
    }
    & docker compose --profile recovery cp $backup restore-db:/tmp/railsync-restore.dump
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy backup to isolated restore database' }
    & docker compose --profile recovery exec -T restore-db pg_restore --username=railsync_restore --dbname=railsync_restore --exit-on-error --no-owner --no-acl /tmp/railsync-restore.dump
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed' }
    $revision = & docker compose --profile recovery exec -T restore-db psql --username=railsync_restore --dbname=railsync_restore --tuples-only --no-align --command='SELECT version_num FROM alembic_version;'
    if ($LASTEXITCODE -ne 0 -or -not $revision.Trim()) { throw 'Restored migration revision is missing' }
    $restoredTables = & docker compose --profile recovery exec -T restore-db psql --username=railsync_restore --dbname=railsync_restore --tuples-only --no-align --command="SELECT count(*) FROM pg_tables WHERE schemaname='public';"
    Write-Output "Verified isolated restore: migration $($revision.Trim()), $($restoredTables.Trim()) public tables."
}
finally {
    & docker compose --profile recovery exec -T restore-db rm -f /tmp/railsync-restore.dump 2>$null | Out-Null
    Pop-Location
}
