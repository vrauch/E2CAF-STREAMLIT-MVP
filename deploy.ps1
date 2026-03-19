# ─────────────────────────────────────────────────────────────────────────────
# deploy.ps1 — Meridant Matrix full deploy (Windows)
#
# Usage:
#   .\deploy.ps1                               # auto-generated commit message
#   .\deploy.ps1 -Message "Release v1.3"       # custom commit message
#   .\deploy.ps1 -SkipDb                       # push code only, skip DB upload
#   .\deploy.ps1 -SkipCode                     # upload DB only, skip git + fly deploy
#
# What this does:
#   1. git add / commit / push  -> GitHub
#   2. fly deploy               -> Fly.io (rebuilds image from latest code)
#   3. SFTP upload              -> pushes framework DB to Fly.io /data volume
#
# DB flow rules (per ADR-009):
#   Framework DB  (e2caf.db / meridant_frameworks.db) : local -> Fly.io  (via deploy.ps1)
#   Assessment DB (meridant.db)                        : Fly.io -> local  (via db-pull.ps1, NEVER pushed)
#
# Multi-machine dev workflow:
#   Machine A (made changes) : .\deploy.ps1    -> pushes framework DB to prod
#   Machine B (getting sync) : .\db-pull.ps1   -> pulls both DBs from prod
# ─────────────────────────────────────────────────────────────────────────────

param(
    [string]$Message = "",
    [switch]$SkipDb,
    [switch]$SkipCode
)

$ErrorActionPreference = 'Stop'

$APP          = "streamlit-mvp"
$FLY_DATA_DIR = "/data"

function Info    { param($msg) Write-Host ">> $msg" -ForegroundColor White }
function Success { param($msg) Write-Host "OK $msg" -ForegroundColor Green }
function Warn    { param($msg) Write-Host "!! $msg" -ForegroundColor Yellow }
function Fail    { param($msg) Write-Host "XX $msg" -ForegroundColor Red; exit 1 }

# ── Preflight checks ──────────────────────────────────────────────────────────
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "git is not installed" }
if (-not (Get-Command fly -ErrorAction SilentlyContinue)) {
    Fail "fly CLI is not installed. See: https://fly.io/docs/hands-on/install-flyctl/"
}

# Never accidentally push the assessment DB
$tracked = git ls-files --error-unmatch data/meridant.db 2>$null
if ($LASTEXITCODE -eq 0) {
    Fail "data/meridant.db is tracked by git — remove it first:`n  git rm --cached data/meridant.db"
}

# ── Resolve which framework DB to upload ─────────────────────────────────────
$frameworkDb   = $null
$remoteDbName  = $null

if (Test-Path "data\meridant_frameworks.db") {
    $frameworkDb  = "data\meridant_frameworks.db"
    $remoteDbName = "meridant_frameworks.db"
} elseif (Test-Path "data\e2caf.db") {
    $frameworkDb  = "data\e2caf.db"
    $remoteDbName = "e2caf.db"
}

# ── Auto commit message ───────────────────────────────────────────────────────
if ($Message -eq "") {
    $Message = "Deploy $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Git push
# ══════════════════════════════════════════════════════════════════════════════
if (-not $SkipCode) {
    Info "Step 1/3 — Git: commit and push"

    $gitStatus = git status --porcelain
    if ($gitStatus -eq "") {
        Warn "Nothing to commit — working tree is clean. Skipping git commit."
    } else {
        git add -A
        git commit -m $Message
        Success "Committed: `"$Message`""
    }

    git push
    Success "Code pushed to GitHub"
} else {
    Warn "Skipping code push (-SkipCode)"
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Fly deploy
# ══════════════════════════════════════════════════════════════════════════════
if (-not $SkipCode) {
    Info "Step 2/3 — fly deploy -> $APP"
    fly deploy --app $APP
    Success "App deployed to Fly.io"
    Info "Waiting 10 seconds for app to start..."
    Start-Sleep -Seconds 10
} else {
    Warn "Skipping fly deploy (-SkipCode)"
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Upload framework DB via SFTP
# ══════════════════════════════════════════════════════════════════════════════
if (-not $SkipDb) {
    Info "Step 3/3 — Upload framework DB to Fly.io volume"

    if ($null -eq $frameworkDb) {
        Warn "No framework DB found (looked for data\meridant_frameworks.db and data\e2caf.db). Skipping DB upload."
    } else {
        $sizeMB = "{0:N1} MB" -f ((Get-Item $frameworkDb).Length / 1MB)
        Info "Uploading $frameworkDb ($sizeMB) -> $FLY_DATA_DIR/$remoteDbName"

        # Ensure at least one VM is running
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

        "put $frameworkDb $FLY_DATA_DIR/$remoteDbName`nexit" | fly ssh sftp shell --app $APP

        Success "Framework DB uploaded to $FLY_DATA_DIR/$remoteDbName"
    }
} else {
    Warn "Skipping DB upload (-SkipDb)"
}

# ══════════════════════════════════════════════════════════════════════════════
Write-Host ""
Success "Deploy complete — https://$APP.fly.dev"
