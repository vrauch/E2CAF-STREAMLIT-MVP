#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Meridant Matrix full deploy
#
# Usage:
#   ./deploy.sh                          # uses auto-generated commit message
#   ./deploy.sh "Release v1.3 framework" # custom commit message
#   ./deploy.sh --skip-db                # push code only, skip DB upload
#   ./deploy.sh --skip-code              # upload DB only, skip git + fly deploy
#
# What this does:
#   1. git add / commit / push  → GitHub
#   2. fly deploy               → Fly.io (rebuilds image from latest code)
#   3. SFTP upload              → pushes framework DB to Fly.io /data volume
#
# DB flow rules (per ADR-009):
#   Framework DB  (e2caf.db / meridant_frameworks.db) : local → Fly.io  ✓
#   Assessment DB (meridant.db)                        : Fly.io → local  NEVER pushed
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

APP="streamlit-mvp"
FLY_DATA_DIR="/data"

# ── Colours ──────────────────────────────────────────────────────────────────
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${BOLD}▸ $*${RESET}"; }
success() { echo -e "${GREEN}✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠ $*${RESET}"; }
error()   { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
COMMIT_MSG="${1:-}"
SKIP_DB=false
SKIP_CODE=false

for arg in "$@"; do
  case "$arg" in
    --skip-db)   SKIP_DB=true ;;
    --skip-code) SKIP_CODE=true ;;
  esac
done

# If first arg is a flag, treat commit message as empty
[[ "$COMMIT_MSG" == --* ]] && COMMIT_MSG=""
[[ -z "$COMMIT_MSG" ]] && COMMIT_MSG="Deploy $(date '+%Y-%m-%d %H:%M')"

# ── Preflight checks ──────────────────────────────────────────────────────────
command -v git  >/dev/null || error "git is not installed"
command -v fly  >/dev/null || error "fly CLI is not installed — see https://fly.io/docs/hands-on/install-flyctl/"

# Never accidentally push sensitive files
if git ls-files --error-unmatch data/meridant.db &>/dev/null 2>&1; then
  error "data/meridant.db is tracked by git — remove it first:\n  git rm --cached data/meridant.db"
fi

# ── Resolve which framework DB file to upload ─────────────────────────────────
FRAMEWORK_DB=""
if   [[ -f "data/meridant_frameworks.db" ]]; then
  FRAMEWORK_DB="data/meridant_frameworks.db"
  REMOTE_DB_NAME="meridant_frameworks.db"
elif [[ -f "data/e2caf.db" ]]; then
  FRAMEWORK_DB="data/e2caf.db"
  REMOTE_DB_NAME="e2caf.db"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Git push
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$SKIP_CODE" == false ]]; then
  info "Step 1/3 — Git: commit and push"

  if [[ -z "$(git status --porcelain)" ]]; then
    warn "Nothing to commit — working tree is clean. Skipping git commit."
  else
    git add -A
    git commit -m "$COMMIT_MSG"
    success "Committed: \"$COMMIT_MSG\""
  fi

  git push
  success "Code pushed to GitHub"
else
  warn "Skipping code push (--skip-code)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Fly deploy
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$SKIP_CODE" == false ]]; then
  info "Step 2/3 — fly deploy → $APP"
  fly deploy --app "$APP"
  success "App deployed to Fly.io"
  info "Waiting 10 seconds for app to start..."
  sleep 10
else
  warn "Skipping fly deploy (--skip-code)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Upload framework DB via SFTP
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$SKIP_DB" == false ]]; then
  info "Step 3/3 — Upload framework DB to Fly.io volume"

  if [[ -z "$FRAMEWORK_DB" ]]; then
    warn "No framework DB found (looked for data/meridant_frameworks.db and data/e2caf.db). Skipping DB upload."
  else
    DB_SIZE=$(du -sh "$FRAMEWORK_DB" | cut -f1)
    info "Uploading $FRAMEWORK_DB ($DB_SIZE) → $FLY_DATA_DIR/$REMOTE_DB_NAME"

    # Use heredoc to drive the interactive SFTP shell non-interactively
    printf "put %s %s/%s\nexit\n" \
      "$FRAMEWORK_DB" "$FLY_DATA_DIR" "$REMOTE_DB_NAME" \
      | fly ssh sftp shell --app "$APP"

    success "Framework DB uploaded to $FLY_DATA_DIR/$REMOTE_DB_NAME"
  fi
else
  warn "Skipping DB upload (--skip-db)"
fi

# ══════════════════════════════════════════════════════════════════════════════
echo ""
success "Deploy complete — https://$APP.fly.dev"
