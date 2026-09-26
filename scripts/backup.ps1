param(
    [Parameter(Mandatory=$true)][string]$DestinationDirectory
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$destination = [System.IO.Path]::GetFullPath($DestinationDirectory)
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$name = "railsync-$stamp.dump"
$containerPath = "/tmp/$name"
$output = Join-Path $destination $name

Push-Location $projectRoot
try {
    & docker compose exec -T db pg_dump --username=railsync --dbname=railsync --format=custom --no-owner --no-acl --file=$containerPath
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
    & docker compose cp "db:$containerPath" $output
    if ($LASTEXITCODE -ne 0) { throw 'docker compose cp failed' }
    $hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$output.sha256" -Value "$hash  $name" -Encoding ascii
    Write-Output "Backup: $output"
    Write-Output "SHA256: $hash"
}
finally {
    & docker compose exec -T db rm -f $containerPath 2>$null | Out-Null
    Pop-Location
}
