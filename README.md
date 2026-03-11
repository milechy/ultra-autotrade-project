# Ultra AutoTrade

AI（Claude Opus 4.6 + GPT-4o）が市場ニュースを解析し、Bybit / bitFlyer への取引と Aave でのポジション管理を自動化するシステム。

## アーキテクチャ

```
ニュース入力 (Knowledge Hub)
    ↓
Rule Engine (HF/クールダウン/上限チェック)
    ↓
Phase A: Claude Opus 4.6 判定 → JSON
    ↓ (BUY/SELL かつ cross_validation=true の場合)
Phase B: GPT-4o クロス検証
    ↓
OctoBot シグナル送信
    ↓
Exchange (Bybit/bitFlyer)  +  Aave V3 Rebalance
```

| レイヤー | 技術 |
|----------|------|
| Backend | FastAPI (Python 3.11) — Hetzner VPS (Docker Compose) |
| Frontend | Next.js App Router + shadcn/ui + TailwindCSS — Cloudflare Pages |
| DB | PostgreSQL 16 + pgvector (HNSW) |
| Exchange | Bybit (primary, via ccxt) / bitFlyer (backup) |
| Aave | V3 on Polygon/Arbitrum (web3.py) + Flashbots 対応 |
| AI | Claude Opus 4.6 (Phase A) + GPT-4o (Phase B, BUY/SELL 時のみ) |
| Proxy/DNS | Cloudflare Tunnel → Hetzner backend |

## ディレクトリ構成

```
ultra-autotrade/
├── backend/
│   ├── app/
│   │   ├── knowledge/    # Knowledge Hub (pgvector RAG)
│   │   ├── exchange/     # Bybit/bitFlyer ccxt 抽象化
│   │   ├── ai/           # Two-Phase AI 判定 + Shadow Mode
│   │   ├── aave/         # Aave V3 deposit/withdraw + Flashbots
│   │   ├── bots/         # OctoBot シグナル送信
│   │   ├── automation/   # 監視・レポート・緊急停止
│   │   ├── notifications/# Slack / LINE 通知
│   │   └── auth/         # JWT 認証
│   └── tests/
├── frontend/             # Next.js App Router
├── docs/                 # 設計・運用ドキュメント
└── docker-compose*.yml
```

## クイックスタート（ローカル開発）

### 前提条件

- Docker / Docker Compose
- Python 3.11+
- Node.js 20+

### 1. 環境変数の設定

```bash
cp .env.example .env.local
# .env.local を編集（ANTHROPIC_API_KEY, DATABASE_URL など）
```

### 2. バックエンド起動

```bash
docker compose up -d postgres
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 3. ヘルスチェック

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

API ドキュメント: `http://localhost:8000/docs`

## テスト（DoD 準拠）

```bash
cd backend
ruff check .                                          # lint
ruff format --check .                                 # format
mypy app/ --config-file ../pyproject.toml             # 型チェック
pytest tests/ --cov=app --cov-fail-under=80 -q        # テスト + coverage 80%+
```

## デプロイ

Staging: `docs/deploy_staging.md` を参照。

ブランチ戦略:
```
feature/* → dev → main（PR + レビュー必須）
```

## セキュリティルール（抜粋）

- Private keys は環境変数のみ。ハードコード・ログ出力禁止
- Health Factor < 1.6 → 自動 HARD_STOP
- 最大単回取引: 総資産の 10%
- 日次上限: 総資産の 30%
- LLM 出力は JSON Schema 検証必須。パース失敗 → HOLD

詳細: `docs/13_security_design.md`

## ドキュメント

| ファイル | 内容 |
|----------|------|
| [docs/00_overview.md](docs/00_overview.md) | システム概要 |
| [docs/04_api_design.md](docs/04_api_design.md) | API 設計書 |
| [docs/05_ai_judgement_rules.md](docs/05_ai_judgement_rules.md) | AI 判定ルール |
| [docs/07_aave_operation_logic.md](docs/07_aave_operation_logic.md) | Aave 運用ロジック |
| [docs/13_security_design.md](docs/13_security_design.md) | セキュリティ設計 |
| [docs/14_test_strategy.md](docs/14_test_strategy.md) | テスト戦略 |
| [docs/24_partner_test_guide.md](docs/24_partner_test_guide.md) | パートナーテストガイド |
| [docs/deploy_staging.md](docs/deploy_staging.md) | Staging デプロイ手順 |
