#!/bin/bash
printenv ENV_FILE > .env
printenv AUTH_CONFIG > auth_config.yaml

# Wait for Docker daemon to be ready (DinD can take a few seconds)
until docker info > /dev/null 2>&1; do
  echo "Waiting for Docker daemon..."
  sleep 2
done

docker compose up --build -d