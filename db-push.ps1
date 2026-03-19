# ─────────────────────────────────────────────────────────────────────────────
# db-push.ps1 — Upload databases to Fly.io from local dev machine (Windows)
#
# Usage:
#   .\db-push.ps1 -Frameworks      # push framework DB only (safe, normal workflow)
#   .\db-push.ps1 -Assessments     # push assessment DB (DESTRUCTIVE — overwrites prod)
#   .\db-push.ps1 -Both            # push both DBs (DESTRUCTIVE)
#   .\db-push.ps1 -DryRun          # show what would be pushed, don't upload
#
# WARNING: Pushing the assessment DB overwrites live production data.
#          Only do this for initial setup, seeding, or deliberate restore.
# ─────────────────────────────────────────────────────────────────────────────

param(
    [switch]$Frameworks,
    [switch]$Assessments,
    [switch]$Both,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$APP = "streamlit-mvp"
$FLY_DATA_DIR = "/data"
$LOCAL_DATA = "data"

function Info { param($msg) Write-Host ">> $msg" -ForegroundColor White }
function Success { param($msg) Write-Host "OK $msg" -ForegroundColor Green }
function Warn { param($msg) Write-Host "!! $msg" -ForegroundColor Yellow }
function Fail { param($msg) Write-Host "XX $msg" -ForegroundColor Red; exit 1 }

$PushFrameworks = $Frameworks -or $Both -or (-not $Assessments -and -not $Both)
$PushAssessments = $Assessments -or $Both

# ── Preflight ─────────────────────────────────────────────────────────────────
if (-not (Get-Command fly -ErrorAction SilentlyContinue)) {
    Fail "fly CLI is not installed. See: https://fly.io/docs/hands-on/install-flyctl/"
}

# ── Confirm destructive assessment DB push ────────────────────────────────────
if ($PushAssessments -and -not $DryRun) {
    Write-Host ""
    Warn "WARNING: You are about to overwrite the production assessment database."
    Warn "This will replace all live user data on Fly.io with your local copy."
    Write-Host ""
    $confirm = Read-Host "Type YES to confirm"
    if ($confirm -ne "YES") {
        Fail "Aborted - type exactly YES to proceed"
    }
    Write-Host ""
}

# ── Ensure a VM is running ────────────────────────────────────────────────────
Info "Ensuring a VM is running..."
fly machine start --app $APP 2>$null

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

# ── Helper: push a single file via SFTP ──────────────────────────────────────
function Push-DB {
    param($LocalPath, $RemoteName, $Label)

    if (-not (Test-Path $LocalPath)) { Fail "$Label not found at $LocalPath" }

    $absPath = (Resolve-Path $LocalPath).Path
    $sizeMB  = "{0:N1} MB" -f ((Get-Item $LocalPath).Length / 1MB)
    Info "Pushing ${Label}: $absPath ($sizeMB) -> $FLY_DATA_DIR/$RemoteName"

    if ($DryRun) {
        Warn "[dry-run] Would upload $absPath to $FLY_DATA_DIR/$RemoteName"
        return
    }

    # fly ssh sftp shell's `put` refuses to overwrite existing files, so delete first.
    # fly ssh console --command handles simple shell commands reliably from PowerShell.
    Info "Removing existing remote file (if any)..."
    fly ssh console --app $APP --command "rm -f $FLY_DATA_DIR/$RemoteName" 2>$null

    # Upload via SFTP. PowerShell's pipe sends the text to fly's stdin correctly here
    # because fly ssh sftp shell reads a command stream (not a PTY).
    Info "Uploading via SFTP..."
    "put `"$absPath`" $FLY_DATA_DIR/$RemoteName`nexit" | fly ssh sftp shell --app $APP
    if ($LASTEXITCODE -ne 0) { Fail "SFTP upload failed for $Label (exit code $LASTEXITCODE)" }

    # Verify
    $remoteBytes = fly ssh console --app $APP --command "wc -c < $FLY_DATA_DIR/$RemoteName" 2>$null
    $localBytes  = (Get-Item $LocalPath).Length
    Success "$Label uploaded (local: $localBytes bytes, remote: $($remoteBytes.Trim()) bytes)"
}

# ── Push framework DB ─────────────────────────────────────────────────────────
if ($PushFrameworks) {
    if (Test-Path "$LOCAL_DATA\meridant_frameworks.db") {
        Push-DB "$LOCAL_DATA\meridant_frameworks.db" "meridant_frameworks.db" "Framework DB"
    }
    elseif (Test-Path "$LOCAL_DATA\e2caf.db") {
        Push-DB "$LOCAL_DATA\e2caf.db" "e2caf.db" "Framework DB (legacy name)"
    }
    else {
        Fail "No framework DB found in $LOCAL_DATA\"
    }
}

# ── Push assessment DB ────────────────────────────────────────────────────────
if ($PushAssessments) {
    Push-DB "$LOCAL_DATA\meridant.db" "meridant.db" "Assessment DB"
}

Write-Host ""
Success "Push complete - https://$APP.fly.dev"
