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

    # ── Base64 chunked upload via fly ssh console ──────────────────────────────
    # Avoids all SFTP/stdin-pipe issues on Windows. Encodes the file as base64,
    # appends chunks to a remote staging file, then decodes it in one step.
    $bytes      = [IO.File]::ReadAllBytes($absPath)
    $b64        = [Convert]::ToBase64String($bytes)
    $chunkSize  = 30000
    $totalChunks = [Math]::Ceiling($b64.Length / $chunkSize)

    Info "Uploading in $totalChunks chunks via SSH (this takes ~1-2 min)..."

    # fly ssh console always prints "Connecting to..." to stderr — silence it
    $ErrorActionPreference = 'SilentlyContinue'

    # Clear / create the remote staging file
    fly ssh console --app $APP --command "python3 -c `"open('/tmp/_db_upload.b64','w').close()`"" 2>$null
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = 'Stop'; Fail "Could not initialise remote staging file" }

    # Send chunks
    for ($i = 0; $i -lt $b64.Length; $i += $chunkSize) {
        $chunk    = $b64.Substring($i, [Math]::Min($chunkSize, $b64.Length - $i))
        $chunkNum = [Math]::Floor($i / $chunkSize) + 1
        Info "  Chunk $chunkNum / $totalChunks"
        fly ssh console --app $APP --command "python3 -c `"open('/tmp/_db_upload.b64','a').write('$chunk')`"" 2>$null
        if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = 'Stop'; Fail "Failed on chunk $chunkNum" }
    }

    # Decode and write to final destination
    Info "Decoding and writing to ${FLY_DATA_DIR}/${RemoteName}..."
    $result = fly ssh console --app $APP --command "python3 -c `"import base64; d=base64.b64decode(open('/tmp/_db_upload.b64').read()); open('$FLY_DATA_DIR/$RemoteName','wb').write(d); open('/tmp/_db_upload.b64','w').close(); print('Written',len(d),'bytes')`"" 2>$null
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = 'Stop'; Fail "Failed to finalise upload: $result" }

    $ErrorActionPreference = 'Stop'
    Success "$Label uploaded: $result"
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
