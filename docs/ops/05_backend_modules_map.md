# Ultra AutoTrade — バックエンドモジュールマップ

> 生成: 2026-04-24 / 更新: 2026-05-19（Phase 2 以降追加分を反映）
> `backend/app/` 実コードから抽出（推測なし）
> FastAPI (Python 3.11)、SQLAlchemy、PostgreSQL 16

---

## 1. main.py ルーター登録順序

`backend/app/main.py` の `include_router` 呼び出し順（上から実行順）:

| # | モジュール | prefix | tags | 備考 |
|---|-----------|--------|------|------|
| 1 | auth | `/auth` | auth | Phase12 |
| ~~2~~ | ~~invitations~~ | ~~`/api/invitations`~~ | — | **コメントアウト済** (Phase 2 物理削除予定 → `/partner/referral` に置換) |
| 2 | partner | `/api/partner` | partner | Wave 2 |
| 3 | allocation | `/api/partner` | partner-allocations | 資金割り振り |
| 4 | users | `/users` | users | Phase12 |
| 5 | ai | `/api/ai` | — | Phase2 |
| 6 | octobot (bots) | — | — | Phase3 |
| 7 | aave | `/api/aave` | — | Phase4 |
| 8 | rebalance | `/api` | — | Aave Rebalance (Stream-T) |
| 9 | knowledge | `/knowledge` | — | PoC Pivot Step 2 |
| 10 | dca | `/dca` | — | DCA Bot |
| 11 | exchange | `/exchange` | — | PoC Pivot Step 3 |
| 12 | rss | `/rss` | — | RSS 自動取得 |
| 13 | webhook | `/webhook` | — | Webhook 受信 |
| 14 | hooks | `/api/hooks` | — | Slack 承認ゲート |
| 15 | automation | — | — | ワークフロー |
| 16 | transparency | — | — | Wave 2 |
| 17 | fee (aave) | — | — | 手数料計算 CSV (aave/fee_router) |
| 18 | automation_dashboard | `/api/automation` | — | 自動化ダッシュボード |
| 19 | data_feeds | `/api/data-feeds` | — | Phase 2 外部データ |
| 20 | reports | `/api/reports` | — | 月次レポート |
| 21 | fees_v10 | `/api/v1/fees` | fees-v10 | **Fee Model v10 API (F-1〜F-16)** |
| 22 | billing | `/api/billing` | — | 請求 |
| 23 | ai_decisions | — | — | AI判定 API |
| 24 | ai_feedback | — | — | AI フィードバック (Layer 4) |
| 25 | transactions | `/api/transactions` | — | トランザクション |
| 26 | admin_transactions | — | — | admin 用トランザクション |
| 27 | proposals | `/api/proposals` | — | 提案 API |
| 28 | portfolio | `/api/portfolio` | — | ポートフォリオ履歴 |
| 29 | user_settings | — | — | ユーザー設定 |
| 30 | alias | — | — | `/api/safety-score` 等エイリアス |
| 31 | notification | `/notifications` | — | PWA 通知 |
| 32 | notification_api | `/api/notifications` | — | PWA 通知エイリアス |
| 33 | lido | `/api/protocols/lido` | lido | **Lido Finance (Phase 2)** |
| 34 | pendle | `/api/protocols/pendle` | pendle | **Pendle Finance (Phase 2)** |
| 35 | protocol_health | `/api/protocols/health` | protocol-health | **プロトコルヘルスモニター (Phase 2)** |
| 36 | referral | `/partner/referral` | referral | **紹介コード / Partner Affiliate (RAS Lane 2)** |
| 37 | health_detail | — | — | **`/health/detail` (admin, 2026-05-14)** |

特殊エンドポイント (inline):
- `GET /health` — スケジューラー・DB・接続状態を返す
- `GET /health/detail` — 詳細ヘルスチェック (admin 認証必須、`health/detail_router.py`)

---

## 2. モジュール別詳細

### auth `/auth`
**役割:** JWT 発行、bcrypt 認証、ロール管理、利用規約同意  
**主要クラス:** `AuthService`  
**エンドポイント数:** 11 (GET×3, POST×7, PUT×1)  
**主要スキーマ:** `RegisterRequest`, `LoginRequest`, `TokenResponse`, `UserResponse`, `UserRole`, `InvestmentTier`

### users `/users`
**役割:** ユーザー CRUD、手数料スケジュール、招待  
**エンドポイント数:** 8 (GET×5, POST×1, PUT×1, DELETE×1)  
**依存:** `AuthService`, `FeeRateRange`  
**主要スキーマ:** `UserCreateRequest`, `UserUpdateRequest`, `PasswordChangeRequest`

### partner `/api/partner`
**役割:** パートナー KPI 統計、月次実績、配下ユーザー一覧  
**エンドポイント数:** 5 (GET×5)  
**主要スキーマ:** `PartnerStatsResponse`, `UserStatsResponse`, `MonthlyStatsResponse`, `NotificationLogPage`, `TesterItem`

### proposals `/api/proposals`
**役割:** AI 提案の CRUD、承認・拒否・実行  
**エンドポイント数:** 8 (GET×5, POST×3)  
**依存:** `notifications.factory` (承認時), `aave.service.MultiChainAaveService` (実行時)  
**主要スキーマ:** `ProposalCreate`, `ProposalResponse`, `AdminProposalListResponse`, `AdminProposalStats`

### ai `/api/ai`
**役割:** マルチ LLM 判定 (Claude + GPT-4o)、RAG コンテキスト注入、的中率  
**主要クラス:** `AIService`  
**エンドポイント数:** 4 (GET×3, POST×1)  
**主要スキーマ:** `AIAnalysisRequest`, `AIAnalysisResult`, `TradeAction`, `LLMDecision`, `CrossValidationResult`

### aave `/api/aave`
**役割:** Aave V3 (Base) への deposit/withdraw/health_factor/monitor  
**主要クラス:** `AaveService`, `MultiChainAaveService`, `RiskLimitError`  
**エンドポイント数:** 4 (GET×3, POST×1)  
**主要スキーマ:** `AaveRebalanceRequest`, `AaveOperationResult`, `AaveBalanceInfo`, `AaveMonitorStatus`

### exchange `/exchange`
**役割:** Bybit (ccxt) 注文実行、取引所ステータス  
**主要クラス:** `ExchangeService`  
**エンドポイント数:** 2 (GET×1, POST×1)  
**主要スキーマ:** `OrderRequest`, `OrderResult`, `ExchangeStatusResponse`

### knowledge `/knowledge`
**役割:** RAG パイプライン (スクレイプ → チャンク → embed → pgvector 検索)  
**主要クラス:** `KnowledgeService`  
**エンドポイント数:** 6 (GET×2, POST×3, PUT×1)  
**主要スキーマ:** `KnowledgeCreateRequest`, `KnowledgeItem`, `KnowledgeSearchRequest`, `KnowledgeSearchResponse`

### automation (prefix なし)
**役割:** E2E ワークフロー管理、スケジューラー、緊急停止、モニタリング  
**主要クラス:** `MonitoringService` (シングルトン: `get_monitoring_service()`), `ShadowModeService`, `StressController`  
**エンドポイント数:** 4 (GET×3, POST×1)  
**主要スキーマ:** `AutomationStatus`, `WorkflowRunResult`, `HealthFactorStatus`, `DashboardSnapshot`

### notifications `/notifications` + `/api/notifications`
**役割:** Slack / LINE / DB への通知送信・ログ  
**主要クラス:** `CompositeNotificationService`, `DualChannelNotificationService`, `DatabaseNotificationSender`  
**エンドポイント数:** 5 (GET×2, POST×2, DELETE×1)  
**主要スキーマ:** `NotificationMessage`, `NotificationSeverity`, `NotificationChannel`

### transactions `/api/transactions`
**役割:** 取引履歴の記録・取得  
**エンドポイント数:** 4 (GET×3, POST×1)  
**主要スキーマ:** `TransactionCreate`, `TransactionResponse`, `TransactionListResponse`, `TransactionStatsResponse`

### billing `/api/billing`
**役割:** 手数料計算、請求期間管理  
**エンドポイント数:** 4 (GET×3, POST×1)  
**主要スキーマ:** `FeeConfigResponse`, `FeeCalculationResponse`, `FeeSummaryResponse`

### dca `/dca`
**役割:** DCA Bot 設定・実行、Grid Bot 設定  
**エンドポイント数:** 6 (GET×3, POST×3)  
**主要スキーマ:** `DCAConfig`, `DCAExecutionResult`, `GridConfigRequest`, `GridStatusResponse`

### data_feeds `/api/data-feeds`
**役割:** 外部価格データ・センチメント・マクロ指標取得  
**エンドポイント数:** 9 (GET×4, POST×5)

### invitations `/api/invitations`
**役割:** 招待リンク発行・検証  
**エンドポイント数:** 3 (GET×2, POST×1)  
**主要スキーマ:** `InvitationCreateRequest`, `InvitationResponse`, `InvitationValidateResponse`

### portfolio `/api/portfolio`
**役割:** ポートフォリオスナップショット履歴  
**エンドポイント数:** 4 (GET×3, POST×1)  
**主要スキーマ:** `PortfolioSnapshotCreate`, `PortfolioHistoryResponse`, `PortfolioLiveResponse`

### bots (prefix なし)
**役割:** OctoBot シグナル受信  
**エンドポイント数:** 1 (POST×1)  
**主要スキーマ:** `OctoBotSignal`, `OctoBotSignalRequest`

### rss `/rss`
**役割:** RSS フィード自動取得  
**エンドポイント数:** 2 (GET×1, POST×1)

### webhook `/webhook`
**役割:** TradingView / 汎用 Webhook 受信  
**エンドポイント数:** 2 (POST×2)  
**主要スキーマ:** `TradingViewPayload`, `GenericWebhookPayload`

### hooks `/api/hooks`
**役割:** Claude Code Slack 承認ゲート  
**エンドポイント数:** 2 (GET×1, POST×1)

### notion `/notion` (レガシー)
**役割:** Notion インジェスト (廃止予定→knowledge に移行)  
**エンドポイント数:** 1

---

## 2b. Phase 2 以降追加モジュール（2026-05-19 反映）

### protocols/lido `/api/protocols/lido`
**役割:** Lido Finance V2 — ETH ステーキング・stETH 取得・引き出し・APR 確認  
**主要クラス:** `LidoClient` (DummyClient / Web3 切替)  
**エンドポイント数:** 4 (GET×2, POST×2)  
**エンドポイント:** `GET /status`, `GET /apr`, `POST /stake`, `POST /withdraw`  
**主要スキーマ:** `LidoStatus`, `LidoStakeResponse`, `LidoWithdrawResponse`, `LidoAprResponse`  
**注意:** PoC段階。DummyClient使用中のため staging で `500: DummyClient cannot be used in staging` になる場合あり。

### protocols/pendle `/api/protocols/pendle`
**役割:** Pendle Finance — YT/PT マーケット・mint・redeem・戦略比較  
**主要クラス:** `PendleClient` (DummyClient / Web3 切替)  
**エンドポイント数:** 5 (GET×3, POST×2)  
**エンドポイント:** `GET /markets`, `GET /market/{address}`, `GET /strategies`, `POST /mint`, `POST /redeem`  
**主要スキーマ:** `PendleMarketInfo`, `PendleMintResponse`, `PendleRedeemResponse`, `StrategyComparison`  
**注意:** PoC段階。DummyClient使用中。

### protocols/risk `/api/protocols/health`
**役割:** プロトコルヘルスモニター — Aave / Lido / Pendle 全体の健全性確認  
**主要クラス:** `ProtocolMonitor`, `PegMonitor`, `CompoundRiskAssessor`, `AutoEvacuator`  
**エンドポイント数:** 4 (GET×4)  
**エンドポイント:** `GET /api/protocols/health`, `GET /api/protocols/health/aave`, `GET /api/protocols/health/lido`, `GET /api/protocols/health/pendle`  
**主要スキーマ:** `ProtocolHealth`  
**注意:** `CompoundRiskAssessor` / `AutoEvacuator` は安全装置系 (P0 孤立コード対象)。

### ai/optimizer (ルーター未登録 — PoC schemas-only)
**役割:** AI Optimizer — プロトコル間の配分最適化・戦略スコアリング・ENB (Expected Net Benefit) 計算  
**主要クラス:** `PortfolioAllocator`, `StrategyScorer`, `NetBenefitCalculator`, `StrategyComparator`  
**状態:** schemas + ロジック実装済みだが `app/main.py` に router 未登録 (PoC段階)  
**主要スキーマ:** `OptimizerRequest`, `OptimizerResponse` (`schemas.py`)  
**孤立状態:** P1 (router実装待ち) — `docs/ops/05_backend_modules_map.md` §5 参照

### fees (app/fees/)
**役割:** Fee Model v10 純粋計算エンジン (router なし / `api/v1/fees` router から呼ばれる)  
**主要クラス:** `FeeCalculator`, `TradeGate`  
**注意:** DB / 外部 API 依存なし。純粋関数として実装。エンドポイントは `api/v1/fees` 経由。

### api/v1/fees `/api/v1/fees`
**役割:** Fee Model v10 REST API — 手数料設定取得・計算・請求プレビュー・管理  
**エンドポイント数:** 8 (GET×6, POST×2)  
**主要スキーマ:** `FeeConfigResponse`, `FeeCalculationRequest`, `FeeBillingPreview`  
**依存:** `fees/calculator.py`, `auth.service`

### referral `/partner/referral`
**役割:** Partner Affiliate System (RAS Lane 2) — 紹介コード発行・使用・報酬追跡  
**エンドポイント数:** 3 (GET×2, POST×1)  
**主要スキーマ:** `ReferralCodeCreate`, `ReferralCodeResponse`, `ReferralUsageResponse`  
**注:** 旧 `invitations` router を置換。invitations router は main.py でコメントアウト済み。

### reports `/api/reports`
**役割:** 月次レポート生成 (独立モジュール。旧 `api/automation_dashboard` とは別)  
**エンドポイント数:** 1 (GET×1)  
**エンドポイント:** `GET /api/reports/monthly`  
**依存:** `billing.service`, `transactions.service`

### health `/health/detail`
**役割:** 詳細ヘルスチェック — DB 接続・スケジューラー状態・各サービス ping を詳細報告  
**主要クラス:** `HealthDetailResponse` (schemas.py)  
**エンドポイント数:** 1 (GET×1)  
**エンドポイント:** `GET /health/detail` (admin 認証必須)  
**依存:** `automation.monitoring_service`, `database`

### utils (ライブラリ — ルーター非登録)
**役割:** 共通ユーティリティ  
**主要ファイル:**  
- `masking.py` — トークン・秘密鍵のマスク (先頭6字+末尾4字)  
- `cache.py` — インメモリキャッシュユーティリティ  
**注意:** ルーター非登録。各モジュールから `from app.utils.masking import mask_secret` 等でインポートして使用。

---

## 3. モジュール間依存関係

### workflow.py が呼ぶサービス
```
automation/workflow.py
├── ai.service.AIService
├── automation.monitoring_service.MonitoringService  ← シングルトン必須
├── automation.shadow_mode_service.ShadowModeService
├── bots.service.OctoBotService
├── exchange.service.ExchangeService
├── knowledge.service.KnowledgeService
├── notion.service.NotionService  (レガシー)
└── notifications.service  (遅延インポート: 承認時)
```

### AI Optimizer の依存 (Phase 2 / PoC)
```
ai/optimizer/
├── allocator.py (PortfolioAllocator)
│   └── protocols/risk/compound_risk.py (CompoundRiskAssessor) ← 動的リスクスコア取得
├── comparator.py (StrategyComparator)
├── net_benefit.py (NetBenefitCalculator)
└── strategy_scorer.py (StrategyScorer)
```

### protocols/risk の安全装置依存
```
protocols/risk/
├── auto_evacuate.py (AutoEvacuator) ← P0: aave/service に配線確認必要
├── compound_risk.py (CompoundRiskAssessor) ← ai/optimizer が参照
├── peg_monitor.py (PegMonitor) ← stETH/PT peg 監視
├── maturity_manager.py (MaturityManager) ← Pendle YT 満期管理
└── protocol_monitor.py (ProtocolMonitor) ← router から呼ばれる
```

### proposals/router.py の依存
```
proposals/router.py
├── notifications.factory.get_notification_service  (承認時, 遅延インポート)
└── aave.service.MultiChainAaveService  (実行時, 遅延インポート)
```

### users/router.py の依存
```
users/router.py
├── auth.service.AuthService
└── users.fee_service.FeeRateRange / get_full_fee_schedule
```

---

## 4. 認証レベル別エンドポイント数

| モジュール | 合計 | require_admin | require_partner | require_viewer (認証必須) | 公開 |
|-----------|------|--------------|----------------|--------------------------|------|
| auth | 11 | 0 | 0 | ~5 | ~6 (login/register 等) |
| users | 8 | 2 | 6 | — | 0 |
| partner | 5 | 0 | 5 (全て) | — | 0 |
| proposals | 8 | 2 | 5 | 1 | 0 |
| ai | 4 | 0 | 0 | ~4 | 0 |
| aave | 4 | 2 | 0 | 2 | 0 |
| exchange | 2 | 0 | 0 | 2 | 0 |
| knowledge | 6 | 2 | 0 | 4 | 0 |
| notifications | 5 | 2 | 0 | 3 | 0 |
| transactions | 4 | 2 | 0 | 2 | 0 |
| billing | 4 | 2 | 0 | 2 | 0 |
| data_feeds | 9 | 5 | 0 | 4 | 0 |
| dca | 6 | 0 | 0 | 6 | 0 |
| invitations | 3 | 1 | 0 | 1 | 1 |
| portfolio | 4 | 0 | 0 | 4 | 0 |
| bots | 1 | 0 | 0 | 0 | 1 (INTERNAL_API_TOKEN) |
| webhook | 2 | 0 | 0 | 0 | 2 (署名検証) |
| hooks | 2 | 0 | 0 | 2 | 0 |
| automation | 4 | 0 | 0 | 4 | 0 |
| rss | 2 | 0 | 0 | 2 | 0 |
| protocols/lido | 4 | 0 | 0 | 4 | 0 |
| protocols/pendle | 5 | 0 | 0 | 5 | 0 |
| protocols/health | 4 | 0 | 0 | 4 | 0 |
| referral | 3 | 0 | 2 | 1 | 0 |
| reports | 1 | 1 | 0 | 0 | 0 |
| fees_v10 | 8 | 4 | 0 | 4 | 0 |
| health/detail | 1 | 1 | 0 | 0 | 0 |

---

## 5. 重要な実装注意事項

### MonitoringService はシングルトン必須
```python
# 正: シングルトン取得
from app.automation.monitoring_service import get_monitoring_service
monitoring = get_monitoring_service()

# 誤: 新規インスタンス化 → 緊急停止フラグが global state に伝わらない
monitoring = MonitoringService()  # NG
```

### DBマイグレーション (Alembic 未使用)
新規カラム追加は Hetzner 本番サーバーで手動 `ALTER TABLE` を実行。
`docs/ops/03_deploy_procedures.md` §DB マイグレーション手順 参照。

### 既知の本番 DB 差分 (2026-04-26 時点)

#### 適用済み
```sql
-- 適用済み (F-2 完了 2026-04-25)
ALTER TABLE users ADD COLUMN IF NOT EXISTS tier VARCHAR(20) NOT NULL DEFAULT 'LOWER';
-- 適用済み (2026-04-24 インシデント対応)
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_judgment_at TIMESTAMP WITH TIME ZONE NULL;
```

#### users.tier の状態 (F-2/F-6 完了後)
- **enum**: `InvestmentTier` — `LOWER` / `MIDDLE` / `UPPER` / `GENERAL` (deprecated, F-13で物理削除予定)
- **DB DEFAULT**: `'LOWER'` (F-2 で `'GENERAL'` から変更済み)
- **normalize_tier()**: LEGACY値 (`GENERAL` 等) を `LOWER` に正規化するヘルパー実装済み (F-6 完了 2026-04-26)
- **既存ユーザー6名**: 現状 `'GENERAL'` のまま (F-16 で `LOWER`/`MIDDLE`/`UPPER` に物理 UPDATE 予定)
- **判定関数**: `app.users.tier_service.determine_tier_jpy()` — JPY 入金額からティア自動判定
- **日本語ラベル**: `app.auth.models.TIER_JP_LABELS` — `LOWER`→ローリスク等の表示変換
