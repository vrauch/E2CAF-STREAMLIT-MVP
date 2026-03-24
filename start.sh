#!/bin/bash
set -euo pipefail

echo "[start.sh] Preparing runtime config files..."

# Materialize .env from ENV_FILE when provided.
if [[ -n "${ENV_FILE:-}" ]]; then
  printf "%s" "$ENV_FILE" > .env
  echo "[start.sh] Wrote .env from ENV_FILE secret."
elif [[ -s .env ]]; then
  echo "[start.sh] ENV_FILE secret missing; using existing .env file."
else
  echo "[start.sh] ERROR: ENV_FILE secret missing and .env does not exist."
  exit 1
fi

# Materialize auth config from either AUTH_CONFIG_B64 or AUTH_CONFIG.
# AUTH_CONFIG_B64 is the safest option for multiline YAML in secret stores.
if [[ -n "${AUTH_CONFIG_B64:-}" ]]; then
  printf "%s" "$AUTH_CONFIG_B64" | base64 -d > auth_config.yaml
  echo "[start.sh] Wrote auth_config.yaml from AUTH_CONFIG_B64 secret."
elif [[ -n "${AUTH_CONFIG:-}" ]]; then
  printf "%s" "$AUTH_CONFIG" > auth_config.yaml
  echo "[start.sh] Wrote auth_config.yaml from AUTH_CONFIG secret."
elif [[ -s auth_config.yaml ]]; then
  echo "[start.sh] AUTH_CONFIG secret missing; using existing auth_config.yaml file."
else
  echo "[start.sh] ERROR: AUTH_CONFIG/AUTH_CONFIG_B64 secret missing and auth_config.yaml does not exist."
  exit 1
fi

# Wait for Docker daemon to be ready (DinD can take a few seconds)
until docker info > /dev/null 2>&1; do
  echo "[start.sh] Waiting for Docker daemon..."
  sleep 2
done

echo "[start.sh] Starting containers (docker compose up --build -d)..."
docker compose up --build -d