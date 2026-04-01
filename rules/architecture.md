# Architecture Reference

## Stack
- Backend: FastAPI (Python 3.11) — Hetzner VPS (Docker Compose)
- Frontend: Next.js App Router + shadcn/ui + TailwindCSS
- DB: PostgreSQL 16 + pgvector (HNSW index, NOT IVFFlat)
- Exchange: bitFlyer (primary, via ccxt) — 日本国内CEX
- Aave: V3 on Base Sepolia (testnet) / Arbitrum One (production) — web3.py
- AI: Claude Opus 4.6 (primary judge) + GPT-4o (cross-verify on BUY/SELL only)
- Proxy/DNS: Cloudflare Tunnel → Hetzner backend

## Execution Order (Rule Engine BEFORE LLM)
1. Rule engine: HF < 1.6? → HOLD (skip LLM call, save cost)
2. Rule engine: cooldown active? → HOLD
3. Rule engine: daily limit 30% reached? → HOLD
4. RAG: Knowledge Hub → context generation
5. Phase A: Claude Opus judgment → JSON
6. Phase B: (conditional) GPT-4o cross-verify on BUY/SELL
7. Rule engine: final guardrail check
8. Execution: ccxt → bitFlyer

## Key API Endpoints
- POST /knowledge/items — register knowledge
- GET  /knowledge/items?status=pending — fetch unprocessed items
- POST /knowledge/search — RAG vector search
- POST /ai/analyze — multi-LLM BUY/SELL/HOLD judgment
- POST /octobot/signal — OctoBot signals
- POST /aave/rebalance — Aave deposit/withdraw with safety
- POST /exchange/order — ccxt → exchange order execution
- GET  /exchange/status — exchange connection & balance

## Directory Structure
```
backend/app/
├── knowledge/     # PostgreSQL + pgvector
├── exchange/      # ccxt abstraction (bitFlyer)
├── ai/            # multi-LLM judge + JSON Schema
├── aave/          # web3.py Aave V3
├── bots/          # OctoBot signals
├── automation/    # monitoring, reporting, emergency stop
└── notifications/ # Slack/LINE
```
