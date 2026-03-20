# Ultra AutoTrade — Staging Deploy Guide

## Prerequisites

- Hetzner VPS (Ubuntu 24.04, CX22 or higher)
- Cloudflare account (for Tunnel)
- API keys: Anthropic, OpenAI, Bybit (Sandbox)

## Initial Setup

### 1. VPS Setup

```bash
# SSH into VPS
ssh root@YOUR_HETZNER_IP

# Run setup script
curl -sSL https://raw.githubusercontent.com/milechy/ultra-autotrade-project/staging/scripts/hetzner_setup.sh | bash
```

### 2. Clone & Configure

```bash
cd /opt/ultra-autotrade
git clone https://github.com/YOUR_ORG/ultra-autotrade-project.git .
git checkout staging

# Create environment file
cp .env.staging.example .env.staging
nano .env.staging  # Fill in API keys
```

### 3. Deploy

```bash
chmod +x deploy.sh
./deploy.sh staging
```

### 4. Verify

```bash
# Health check
curl http://localhost:8000/health

# Check logs
docker compose -f docker-compose.staging.yml logs -f backend
```

## Cloudflare Tunnel

```bash
# Install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i cloudflared.deb

# Create tunnel
cloudflared tunnel login
cloudflared tunnel create ultra-autotrade

# Configure (create ~/.cloudflared/config.yml)
cat > ~/.cloudflared/config.yml << EOF
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: staging-api.ultra-autotrade.com
    service: http://localhost:8000
  - service: http_status:404
EOF

# Start as service
cloudflared service install
systemctl start cloudflared
```

## CI/CD Auto-Deploy

Push to `staging` branch triggers automatic deploy via GitHub Actions.

Required secrets:
- `HETZNER_SSH_KEY`: SSH private key for VPS
- `HETZNER_HOST`: VPS IP address

## Monitoring

```bash
# Container status
docker compose -f docker-compose.staging.yml ps

# Backend logs
docker compose -f docker-compose.staging.yml logs -f backend

# PostgreSQL logs
docker compose -f docker-compose.staging.yml logs -f postgres

# Disk usage
df -h
docker system df
```

## Rollback

```bash
# Revert to previous commit
git log --oneline -5
git checkout <previous_commit>
./deploy.sh staging
```

## Security Checklist

- [ ] `.env.staging` is NOT in git
- [ ] `BYBIT_SANDBOX=true` in staging
- [ ] `AAVE_CLIENT_TYPE=dummy` until Sepolia is configured
- [ ] JWT_SECRET_KEY is unique random value
- [ ] UFW firewall enabled (only 22, 80, 443)
- [ ] fail2ban running
- [ ] Cloudflare Tunnel active (port 8000 not exposed)
