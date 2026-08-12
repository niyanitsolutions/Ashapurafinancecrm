# Stops and removes every Full Docker Mode container (data volumes are kept - pass -v
# to also wipe them). If you were instead in Development Mode, use env-dev-down.ps1.
$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RootDir

docker compose -f deployment/docker-compose.yml down
