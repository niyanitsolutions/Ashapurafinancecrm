# Internal helper used by start-local.sh (via `pwsh -File`) to spawn a hidden,
# log-redirected background process. Not meant to be run by hand.
# start-local.ps1 does not need this — it calls Start-Process directly.
#
# Writes the spawned PID to -PidFile rather than stdout: Start-Process's own child
# (whatever -FilePath is, e.g. a long-running uvicorn/npm dev server) can end up
# inheriting this process's original stdout handle when RedirectStandardOutput/Error
# are used (a known Windows CreateProcess handle-inheritance quirk) — if the caller were
# reading the PID via a pipe/command substitution instead, it would block forever
# waiting for EOF that never comes, because the long-running grandchild still holds that
# handle open. A plain file has no such problem.
param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $true)][string]$Arguments,
    [Parameter(Mandatory = $true)][string]$WorkingDirectory,
    [Parameter(Mandatory = $true)][string]$LogFile,
    [Parameter(Mandatory = $true)][string]$PidFile
)
$ErrorActionPreference = "Stop"
$argArray = $Arguments -split ' '
$p = Start-Process -FilePath $FilePath -ArgumentList $argArray -WorkingDirectory $WorkingDirectory `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err"
Set-Content -Path $PidFile -Value $p.Id -NoNewline
