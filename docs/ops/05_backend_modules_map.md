# Ultra AutoTrade — バックエンドモジュールマップ

> 生成: 2026-04-24 / `backend/app/` 実コードから抽出（推測なし）
> FastAPI (Python 3.11)、SQLAlchemy、PostgreSQL 16

---

## 1. main.py ルーター登録順序

`backend/app/main.py` の `include_router` 呼び出し順（上から実行順）:

| # | モジュール | prefix | tags | 備考 |
|---|-----------|--------|------|------|
| 1 | auth | `/auth` | auth | Phase12 |
| 2 | invitations | `/api/invitations` | — | Wave 2 |
| 3 | partner | `/api/partner` | partner | Wave 2 |
| 4 | allocation | `/api/partner` | partner-allocations | 資金割り振り |
| 5 | users | `/users` | users | Phase12 |
| 6 | ai | `/api/ai` | — | Phase2 |
| 7 | octobot (bots) | — | — | Phase3 |
| 8 | aave | `/api/aave` | — | Phase4 |
| 9 | rebalance | `/api` | — | Aave Rebalance (Stream-T) |
| 10 | knowledge | `/knowledge` | — | PoC Pivot Step 2 |
| 11 | dca | `/dca` | — | DCA Bot |
| 12 | exchange | `/exchange` | — | PoC Pivot Step 3 |
| 13 | rss | `/rss` | — | RSS 自動取得 |
| 14 | webhook | `/webhook` | — | Webhook 受信 |
| 15 | hooks | `/api/hooks` | — | Slack 承認ゲート |
| 16 | automation | — | — | ワークフロー |
| 17 | transparency | — | — | Wave 2 |
| 18 | fee | — | — | 手数料計算 CSV |
| 19 | automation_dashboard | `/api/automation` | — | 自動化ダッシュボード |
| 20 | data_feeds | `/api/data-feeds` | — | Phase 2 外部データ |
| 21 | reports | `/api/reports` | — | 月次レポート |
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
| 33 | lido | — | — | Lido Finance (Phase 2) |
| 34 | pendle | — | — | Pendle Finance (Phase 2) |
| 35 | protocol_health | — | — | プロトコルヘルスモニター (Phase 2) |

特殊エンドポイント (inline):
- `GET /health` — スケジューラー・DB・接続状態を返す

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

### 既知の本番 DB 差分 (2026-04-24 時点)
```sql
-- 未適用 (本番DBに存在しないカラム)
ALTER TABLE users ADD COLUMN IF NOT EXISTS tier VARCHAR(20) NOT NULL DEFAULT 'GENERAL';
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_judgment_at TIMESTAMP WITH TIME ZONE NULL;
-- 影響: /auth/me が 500 → AuthProvider がタイムアウト → partner/admin 画面にアクセス不可
```
