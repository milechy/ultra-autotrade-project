#!/usr/bin/env bash
set -euo pipefail

# Ultra AutoTrade — Hetzner VPS Initial Setup
# Run once on a fresh Ubuntu 24.04 VPS
# Usage: curl -sSL <raw_url> | bash

echo "=== Hetzner VPS Setup for Ultra AutoTrade ==="

# Update system
echo "--- Updating system ---"
apt-get update && apt-get upgrade -y

# Install Docker
echo "--- Installing Docker ---"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "Docker installed successfully"
else
    echo "Docker already installed"
fi

# Install Docker Compose plugin
echo "--- Checking Docker Compose ---"
if ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi
docker compose version

# Install basic tools
echo "--- Installing tools ---"
apt-get install -y git curl jq ufw fail2ban

# Firewall setup
echo "--- Configuring UFW firewall ---"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (Cloudflare Tunnel)
ufw allow 443/tcp   # HTTPS (Cloudflare Tunnel)
# Note: ports 3000/8000/3100/5432 are NOT opened here.
# Docker bypasses UFW by default. All ports in docker-compose.production.yml
# are bound to 127.0.0.1 to prevent external access.
# External access is via Cloudflare Named Tunnel only.
ufw --force enable
ufw status

# Fail2ban
echo "--- Configuring fail2ban ---"
systemctl enable fail2ban
systemctl start fail2ban

# Create app directory
echo "--- Setting up app directory ---"
mkdir -p /opt/ultra-autotrade
cd /opt/ultra-autotrade

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Clone repo:  git clone <repo_url> /opt/ultra-autotrade"
echo "  2. Copy env:    cp .env.staging.example .env.staging"
echo "  3. Edit env:    nano .env.staging  (fill in API keys)"
echo "  4. Deploy:      ./deploy.sh staging"
echo "  5. Tunnel:      cloudflared tunnel create ultra-autotrade"
