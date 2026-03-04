#!/usr/bin/env bash
set -euo pipefail

# Ultra AutoTrade — Staging Deploy Script
# Usage: ./deploy.sh [staging|production]

ENV="${1:-staging}"
COMPOSE_FILE="docker-compose.${ENV}.yml"

echo "=== Ultra AutoTrade Deploy (${ENV}) ==="

# Validate
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: $COMPOSE_FILE not found"
    exit 1
fi

if [ ! -f ".env.${ENV}" ]; then
    echo "ERROR: .env.${ENV} not found. Copy from .env.staging.example"
    exit 1
fi

# Pull latest
echo "--- Pulling latest code ---"
git pull origin "$(git branch --show-current)"

# Build and deploy
echo "--- Building containers ---"
docker compose -f "$COMPOSE_FILE" build --no-cache

echo "--- Stopping old containers ---"
docker compose -f "$COMPOSE_FILE" down

echo "--- Starting new containers ---"
docker compose -f "$COMPOSE_FILE" up -d

# Wait for health check
echo "--- Waiting for backend health check ---"
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "Backend is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Backend health check failed after 30 seconds"
        docker compose -f "$COMPOSE_FILE" logs backend --tail 50
        exit 1
    fi
    sleep 1
done

echo "--- Deploy complete ---"
docker compose -f "$COMPOSE_FILE" ps
