# start.ps1 — Activate venv, install deps, and launch the Streamlit app
$ErrorActionPreference = "Stop"

$venvPath = Join-Path $PSScriptRoot ".venv"

# Create the venv if it doesn't exist
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..."
    python -m venv $venvPath
}

# Activate the venv
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
Write-Host "Activating virtual environment..."
& $activateScript

# Install / update dependencies (prefer pre-built wheels to avoid C build errors)
Write-Host "Installing requirements..."
pip install -r (Join-Path $PSScriptRoot "requirements.txt") --quiet --only-binary :all: 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Binary-only install had issues, retrying with source builds allowed..."
    pip install -r (Join-Path $PSScriptRoot "requirements.txt") --quiet
}

# Launch Streamlit
Write-Host "Starting Streamlit app..."
python -m streamlit run (Join-Path $PSScriptRoot "app.py")
