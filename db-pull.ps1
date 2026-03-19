# ─────────────────────────────────────────────────────────────────────────────
# db-pull.ps1 — Download databases from Fly.io to local dev machine (Windows)
#
# Usage:
#   .\db-pull.ps1                  # pull both DBs (frameworks + assessments)
#   .\db-pull.ps1 -Frameworks      # pull framework DB only
#   .\db-pull.ps1 -Assessments     # pull assessment DB only
#   .\db-pull.ps1 -DryRun          # show what would be pulled, don't overwrite
#
# DB flow rules (per ADR-009):
#   Framework DB  (meridant_frameworks.db) : Fly.io -> local  (to sync dev machines)
#   Assessment DB (meridant.db)            : Fly.io -> local  (prod data, read-only on dev)
#
# Run this on any dev machine to get in sync with production.
# ─────────────────────────────────────────────────────────────────────────────

param(
    [switch]$Frameworks,
    [switch]$Assessments,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$APP = "streamlit-mvp"
$FLY_DATA_DIR = "/data"
$LOCAL_DATA = "data"

# If neither flag given, pull both
$PullFrameworks = -not $Assessments
$PullAssessments = -not $Frameworks

function Info { param($msg) Write-Host ">> $msg" -ForegroundColor White }
function Success { param($msg) Write-Host "OK $msg" -ForegroundColor Green }
function Warn { param($msg) Write-Host "!! $msg" -ForegroundColor Yellow }
function Fail { param($msg) Write-Host "XX $msg" -ForegroundColor Red; exit 1 }

# ── Preflight ─────────────────────────────────────────────────────────────────
if (-not (Get-Command fly -ErrorAction SilentlyContinue)) {
    Fail "fly CLI is not installed. See: https://fly.io/docs/hands-on/install-flyctl/"
}
if (-not (Test-Path $LOCAL_DATA)) { New-Item -ItemType Directory -Path $LOCAL_DATA | Out-Null }

# ── Ensure a VM is running ────────────────────────────────────────────────────
Info "Ensuring a VM is running..."
fly machine start --app $APP 2>$null
if ($LASTEXITCODE -ne 0) { } # ignore — machine may already be running

$maxWait = 90
$elapsed = 0
while ($true) {
    $status = fly status --app $APP 2>$null
    if ($status -match "started") { break }
    if ($elapsed -ge $maxWait) { Fail "Timed out waiting for a running VM after ${maxWait}s" }
    Info "  Waiting for VM... (${elapsed}s / ${maxWait}s)"
    Start-Sleep -Seconds 5
    $elapsed += 5
}
Success "VM is running"

# ── Helper: check if a file exists on Fly.io volume ──────────────────────────
function Test-FlyFile {
    param($RemoteName)
    $result = "ls $FLY_DATA_DIR/$RemoteName`nexit" | fly ssh sftp shell --app $APP 2>$null
    return ($result -match $RemoteName)
}

# ── Helper: download a single file via SFTP ──────────────────────────────────
function Receive-DB {
    param($RemoteName, $LocalPath, $Label)

    Info "Pulling ${Label}: $FLY_DATA_DIR/$RemoteName -> $LocalPath"

    if ($DryRun) {
        Warn "[dry-run] Would download $FLY_DATA_DIR/$RemoteName to $LocalPath"
        return
    }

    # Backup existing file
    if (Test-Path $LocalPath) {
        $backup = "$LocalPath.bak"
        Copy-Item $LocalPath $backup -Force
        Warn "Backed up existing file to $backup"
    }

    "get $FLY_DATA_DIR/$RemoteName $LocalPath`nexit" | fly ssh sftp shell --app $APP

    if (-not (Test-Path $LocalPath)) {
        Fail "Download failed - $LocalPath was not created"
    }

    $size = (Get-Item $LocalPath).Length / 1MB
    $sizeFmt = "{0:N1} MB" -f $size
    Success "$Label downloaded ($sizeFmt) -> $LocalPath"
}

# ── Pull framework DB ─────────────────────────────────────────────────────────
if ($PullFrameworks) {
    if (Test-FlyFile "meridant_frameworks.db") {
        Receive-DB "meridant_frameworks.db" "$LOCAL_DATA\meridant_frameworks.db" "Framework DB"
    }
    elseif (Test-FlyFile "e2caf.db") {
        Receive-DB "e2caf.db" "$LOCAL_DATA\e2caf.db" "Framework DB (legacy name)"
    }
    else {
        Warn "No framework DB found on Fly.io volume. Skipping."
    }
}

# ── Pull assessment DB ────────────────────────────────────────────────────────
if ($PullAssessments) {
    if (Test-FlyFile "meridant.db") {
        Receive-DB "meridant.db" "$LOCAL_DATA\meridant.db" "Assessment DB (prod data)"
        Warn "Assessment DB contains production data - do not push this back to Fly.io"
    }
    else {
        Warn "No assessment DB found on Fly.io volume. Skipping."
    }
}

Write-Host ""
Success "Pull complete - local data\ is now in sync with $APP.fly.dev"
