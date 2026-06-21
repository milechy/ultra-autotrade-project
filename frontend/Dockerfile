# Stage 1: Install dependencies
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN \
  if [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
  elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm install --frozen-lockfile; \
  elif [ -f package-lock.json ]; then npm install --legacy-peer-deps; \
  else npm install --legacy-peer-deps; \
  fi

# Stage 2: Build the application
FROM node:20-alpine AS builder
WORKDIR /app

# API URL variables (critical — missing ARG causes Mixed Content on HTTPS deployments)
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Optional build-time variables (empty default is safe)
ARG NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID
ENV NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID=${NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID}
ARG NEXT_PUBLIC_DEFAULT_CHAIN
ENV NEXT_PUBLIC_DEFAULT_CHAIN=${NEXT_PUBLIC_DEFAULT_CHAIN}
ARG NEXT_PUBLIC_DEFAULT_CHAIN_ID
ENV NEXT_PUBLIC_DEFAULT_CHAIN_ID=${NEXT_PUBLIC_DEFAULT_CHAIN_ID}
ARG NEXT_PUBLIC_MAINNET_RPC
ENV NEXT_PUBLIC_MAINNET_RPC=${NEXT_PUBLIC_MAINNET_RPC}
ARG NEXT_PUBLIC_ARBITRUM_ONE_RPC
ENV NEXT_PUBLIC_ARBITRUM_ONE_RPC=${NEXT_PUBLIC_ARBITRUM_ONE_RPC}
ARG NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC
ENV NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC=${NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC}
ARG NEXT_PUBLIC_BASE_RPC
ENV NEXT_PUBLIC_BASE_RPC=${NEXT_PUBLIC_BASE_RPC}
ARG NEXT_PUBLIC_BASE_SEPOLIA_RPC
ENV NEXT_PUBLIC_BASE_SEPOLIA_RPC=${NEXT_PUBLIC_BASE_SEPOLIA_RPC}
ARG NEXT_PUBLIC_OPTIMISM_RPC
ENV NEXT_PUBLIC_OPTIMISM_RPC=${NEXT_PUBLIC_OPTIMISM_RPC}
ARG NEXT_PUBLIC_VAPID_PUBLIC_KEY
ENV NEXT_PUBLIC_VAPID_PUBLIC_KEY=${NEXT_PUBLIC_VAPID_PUBLIC_KEY}
ARG NEXT_PUBLIC_LIFF_ID
ENV NEXT_PUBLIC_LIFF_ID=${NEXT_PUBLIC_LIFF_ID}
ARG NEXT_PUBLIC_PRIVY_APP_ID
ENV NEXT_PUBLIC_PRIVY_APP_ID=${NEXT_PUBLIC_PRIVY_APP_ID}
# PostHog (build-time 埋め込み)。#732 で docker-compose の build.args には追加されたが
# Dockerfile 側の ARG/ENV が欠落しており、キーがビルドに渡らず PostHog が無効化していた不具合を修正。
ARG NEXT_PUBLIC_POSTHOG_KEY
ENV NEXT_PUBLIC_POSTHOG_KEY=${NEXT_PUBLIC_POSTHOG_KEY}
ARG NEXT_PUBLIC_POSTHOG_HOST
ENV NEXT_PUBLIC_POSTHOG_HOST=${NEXT_PUBLIC_POSTHOG_HOST}
# デプロイ版識別子（git short SHA 等）。PostHog 全イベントに app_version として付与し版間比較を可能にする。
ARG NEXT_PUBLIC_APP_VERSION
ENV NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION}

# v4 Phase 2-D-E: 委譲おまかせ consent フローの dormant フラグ（既定 false）。
# true のときのみ OpModePanel の managed 選択で session signer consent を走らせる。
ARG NEXT_PUBLIC_DELEGATION_CONSENT_ENABLED
ENV NEXT_PUBLIC_DELEGATION_CONSENT_ENABLED=${NEXT_PUBLIC_DELEGATION_CONSENT_ENABLED}

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NODE_OPTIONS: Next.js build の OOM 対策 (CLAUDE.md §2026-05-19 GID 1214828243363427)
# docker-compose.staging.yml build.args で NODE_BUILD_MAX_OLD_SPACE_SIZE をオーバーライド可能。
# 実際のピークメモリは staging で `docker stats` → `npm run build` 実行後に確認すること。
# 推測での値変更は禁止 (実ビルドログでピーク確認後に設定)。
ARG NODE_BUILD_MAX_OLD_SPACE_SIZE=4096
ENV NODE_OPTIONS="--max-old-space-size=${NODE_BUILD_MAX_OLD_SPACE_SIZE}"

# Ensure standalone output is enabled
RUN if ! grep -q "output.*standalone" next.config.* 2>/dev/null; then \
  echo "/** @type {import('next').NextConfig} */" > next.config.mjs.bak && \
  echo "const nextConfig = { output: 'standalone' };" >> next.config.mjs.bak && \
  echo "export default nextConfig;" >> next.config.mjs.bak && \
  mv next.config.mjs.bak next.config.mjs; \
  fi

RUN mkdir -p /app/public && npm run build
RUN ls -la /app/.next/ || echo "NO .next DIRECTORY"
RUN ls /app/.next/standalone && ls /app/ || echo "PATH ISSUE"

# Stage 3: Production runner
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

RUN mkdir -p /app/public /app/.next
COPY --from=builder /app/public/ /app/public/

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone/ /app/
COPY --from=builder --chown=nextjs:nodejs /app/.next/static/ /app/.next/static/
COPY --from=builder --chown=nextjs:nodejs /app/messages/ /app/messages/

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
