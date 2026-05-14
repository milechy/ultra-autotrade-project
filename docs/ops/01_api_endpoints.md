# Ultra AutoTrade — API エンドポイント一覧

> 生成: 2026-04-24 / ソース: `backend/app/*/router.py` + `main.py`
> ベースURL: `https://api.ultra-auto-trade.com` (本番) / `http://localhost:8001` (staging)

---

## 凡例

| 記号 | 意味 |
|------|------|
| 🔓 | 認証不要 |
| 🔑 | JWT Bearer token 必要 (`Authorization: Bearer <token>`) |
| 👤 | viewer 以上（テスター・partner・admin） |
| 🤝 | partner 以上（admin含む） |
| 👑 | admin のみ |

---

## ヘルスチェック

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/health` | 🔓 | アプリ生死確認。`scheduler_healthy`, `warnings` フィールドに注意 |
| GET | `/health/detail` | 🔑 admin | 4軸多層ヘルス (scheduler/quota/cross_judgment/safety) + warnings + 5min キャッシュ。F-17a 期限切れ・OpenAI/Perplexity quota・cross-judgment 停止を観測可能化 (5/14 DoD #6) |

---

## 認証 `/auth`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/auth/register` | 🔓 | ユーザー登録（`INITIAL_ADMIN_EMAIL` 未設定時は無効化） |
| POST | `/auth/login` | 🔓 | ログイン → JWT返却 |
| POST | `/auth/logout` | 🔑 | ログアウト |
| GET | `/auth/me` | 🔑 | 現在ユーザー情報 |
| POST | `/auth/change-password` | 🔑 | パスワード変更 |
| GET | `/auth/terms/status` | 🔑 | 利用規約承諾状態確認 |
| POST | `/auth/terms/accept` | 🔑 | 利用規約承諾 |
| GET | `/auth/risk-mode` | 🔑 | リスクモード取得 |
| PUT | `/auth/risk-mode` | 🔑 | リスクモード更新 |
| POST | `/auth/wallet/connect` | 🔑 | WalletConnect認証 |
| POST | `/auth/wallet/link` | 🔑 | 認証済みユーザーへのウォレット紐付け (200/401/409/422/404, F-17 L1) |
| POST | `/auth/line` | 🔓 | LINE LIFF認証 → JWT返却 |

---

## AI `/api/ai`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/api/ai/analyze` | 🔑 | ニュースのAI解析（BUY/SELL/HOLD判定） |
| GET | `/api/ai/trend/confidence` | 🔑 | 信頼度トレンド取得 |
| GET | `/api/ai/sentiment/history` | 🔑 | Xセンチメント時系列 |
| GET | `/api/ai/accuracy` | 🔑 | AI判定的中率サマリー |

## AI 判定 `/api/ai/decisions`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/ai/decisions/latest` | 🔑 | 最新AI判定 |
| GET | `/api/ai/decisions` | 🔑 | AI判定履歴リスト |
| GET | `/api/ai/decisions/{decision_id}` | 🔑 | AI判定詳細 |
| POST | `/api/ai/decisions` | 🔑 | AI判定記録（内部用） |

## AI フィードバック `/api/ai/feedback`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/api/ai/feedback/record` | 🔑 | フィードバック記録 |
| GET | `/api/ai/feedback/stats` | 🔑 | フィードバック統計 |
| GET | `/api/ai/feedback/{decision_id}` | 🔑 | 判定別フィードバック |

---

## Aave `/api/aave`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/api/aave/rebalance` | 🔑 | BUY/SELL/HOLD に応じて Aave ポジション調整 |
| GET | `/api/aave/chains/health` | 🔑 | 全アクティブチェーンの Health Factor |
| GET | `/api/aave/health-factor` | 🔑 | Aave V3 Health Factor リアルタイム取得 |
| GET | `/api/aave/status` | 🔑 | Aave ポジション状態（HF + 残高） |

## Aave リバランス `/api/aave/rebalance`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/aave/rebalance/status` | 🔑 | リバランス状態 |
| POST | `/api/aave/rebalance/simulate` | 🔑 | リバランスシミュレーション |
| POST | `/api/aave/rebalance/execute` | 👑 | リバランス実行 |
| GET | `/api/aave/rebalance/history` | 🔑 | リバランス履歴 |

## 透明性レポート `/api/transparency`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/transparency/safety-score` | 🔑 | 安全スコア |
| GET | `/api/transparency/explanation/{decision_id}` | 🔑 | 判定説明 |
| GET | `/api/transparency/signal` | 🔑 | シグナル情報 |
| GET | `/api/transparency/impact` | 🔑 | 影響評価 |
| GET | `/api/transparency/simulation` | 🔑 | シミュレーション |
| GET | `/api/transparency/performance` | 🔑 | パフォーマンス |
| GET | `/api/transparency/performance/monthly` | 🔑 | 月次パフォーマンス |
| GET | `/api/transparency/risk-profile` | 🔑 | リスクプロファイル |
| GET | `/api/transparency/risk-profile/{mode}` | 🔑 | モード別リスクプロファイル |

## 手数料計算 `/api/fees` (v9 旧、F-8b で廃止予定)

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/fees/calculate` | 🔑 | 手数料計算 (旧) |
| GET | `/api/fees/schedule` | 🔑 | 手数料スケジュール (旧) |

> **DEPRECATED**: F-8b (Asana 1214288467406433) で廃止予定。F-8a で `/api/v1/fees/*` (下記) に置換。
> 本タスク (F-8a, PR #126 以降) では併存中。

## 手数料 v10 `/api/v1/fees` (F-8a 新規)

Fee Model v10 read-only 中心 + simulate。F-1〜F-5 (FeeConfigV10 / FeeTransaction / FeeCalculator) を消費する。

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET  | `/api/v1/fees/config`              | 🔑 | 現行 active fee_config 取得 |
| GET  | `/api/v1/fees/my-summary`          | 🔑 | 自分の累計手数料サマリ |
| GET  | `/api/v1/fees/my-history`          | 🔑 | 自分の月別履歴 (最新 N 件、`?limit=N`) |
| POST | `/api/v1/fees/simulate`            | 🔑 | v10 計算シミュレーション (DB 書込なし) |
| GET  | `/api/v1/fees/affiliate-earnings` | 🔑 | 自分が招待者として記録された月別 affiliate 報酬 |
| GET  | `/api/v1/fees/all-users`           | 👑 | 全ユーザー手数料一覧 (`?month=YYYY-MM-DD`) |
| POST | `/api/v1/fees/finalize-month`      | 👑 | 月次 finalize (現状 501、F-7 で本実装) |
| GET  | `/api/v1/fees/uata-income`         | 👑 | UATa 収入集計 (`?month_from&month_to`) |

**Decimal 返却**: 金額系フィールドは Decimal を文字列で返す (例: `"3000"` `"0.30"`)。フロントは `Number(str).toFixed()` で扱う (CLAUDE.md "Decimal型 → Number() ラップ" メモリ準拠)。

---

## Exchange `/exchange`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/exchange/order` | 🔑 | 注文発注（Bybit経由） |
| GET | `/exchange/status` | 🔑 | 取引所接続・残高状態 |

---

## Proposals `/api/proposals`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/proposals/admin/all` | 👑 | 全ユーザー提案一覧（管理者） |
| GET | `/api/proposals/admin/stats` | 👑 | 提案KPI統計（管理者） |
| GET | `/api/proposals/pending` | 🔑 | 保留中の提案リスト |
| GET | `/api/proposals/history` | 🔑 | 提案履歴 |
| POST | `/api/proposals/{proposal_id}/approve` | 🤝 | 提案承認・実行 |
| POST | `/api/proposals/{proposal_id}/reject` | 🤝 | 提案拒否 |
| GET | `/api/proposals/{proposal_id}` | 🔑 | 提案詳細 |
| POST | `/api/proposals` | 🔑 | 提案作成 |

---

## Transactions `/api/transactions`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/transactions/stats` | 👤 | 取引統計 |
| GET | `/api/transactions` | 👤 | 取引履歴リスト (`limit`, `offset` query) |
| GET | `/api/transactions/{transaction_id}` | 👤 | 取引詳細 |
| POST | `/api/transactions` | 🔑 | 取引記録（内部用） |

## Admin Transactions `/api/admin/transactions`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/admin/transactions/stats` | 👑 | 管理者用取引統計 |
| GET | `/api/admin/transactions` | 👑 | 全ユーザー取引リスト |
| GET | `/api/admin/transactions/{transaction_id}` | 👑 | 取引詳細 |

---

## Portfolio `/api/portfolio`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/portfolio` | 🔑 | ライブAaveポートフォリオ (`?chain=arbitrum_sepolia`) |
| GET | `/api/portfolio/current` | 👤 | 現在のポートフォリオ |
| GET | `/api/portfolio/history` | 👤 | 資産推移履歴 (`?period=30d&interval=daily`) |
| POST | `/api/portfolio/snapshot` | 🔑 | スナップショット記録（内部用） |

---

## Users `/users`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/users` | 👑 | ユーザー一覧 |
| POST | `/users` | 👑 | ユーザー作成 |
| GET | `/users/fee-schedule` | 🔑 | ティア別手数料体系 |
| GET | `/users/{user_id}` | 👑 | ユーザー詳細 |
| PUT | `/users/{user_id}` | 👑 | ユーザー更新 |
| DELETE | `/users/{user_id}` | 👑 | ユーザー削除 |
| GET | `/users/{user_id}/tier` | 🔑 | ユーザーティア情報 |
| GET | `/users/{user_id}/fee-info` | 🔑 | ユーザー手数料情報 |

## User Settings `/api/user`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/user/settings` | 🔑 | 設定取得 |
| PUT | `/api/user/settings` | 🔑 | 設定更新 |
| GET | `/api/user/my-allocation` | 🔑 | 自分の配分情報 |
| POST | `/api/user/pause` | 🔑 | 運用一時停止 |
| POST | `/api/user/resume` | 🔑 | 運用再開 |

---

## Partner `/api/partner`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/partner/testers` | 🤝 | テスター一覧 |
| GET | `/api/partner/stats` | 🤝 | パートナー統計 |
| GET | `/api/partner/users/{user_id}/stats` | 🤝 | ユーザー別統計 |
| GET | `/api/partner/monthly` | 🤝 | 月次サマリー |
| GET | `/api/partner/notifications` | 🤝 | 通知一覧 |
| GET | `/api/partner/allocations` | 🤝 | 配分一覧 |
| POST | `/api/partner/allocations` | 🤝 | 配分作成 |
| PUT | `/api/partner/allocations/{allocation_id}` | 🤝 | 配分更新 |
| DELETE | `/api/partner/allocations/{allocation_id}` | 🤝 | 配分削除 |
| GET | `/api/partner/performance` | 🤝 | パフォーマンス |

---

## Invitations `/api/invitations`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/api/invitations` | 🤝 | 招待コード作成 |
| GET | `/api/invitations` | 🤝 | 自分の招待コード一覧 |
| GET | `/api/invitations/{code}` | 🔓 | 招待コード検証 |

---

## Billing `/api/billing` (v9 旧、F-8b で廃止予定)

> **DEPRECATED**: F-8b (Asana 1214288467406433) で廃止予定。`/api/v1/fees/*` (上記) に置換。
> 本タスク (F-8a) 時点では併存中。フロント差し替えも F-8b で対応。


| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/billing/fees` | 👑 | 手数料計算一覧 |
| GET | `/api/billing/summary` | 🔑 | 手数料サマリー |
| POST | `/api/billing/batch/daily` | 👑 | 日次バッチ処理 |
| GET | `/api/billing/config` | 👑 | 手数料設定 |

---

## Knowledge Hub `/knowledge`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/knowledge/items` | 🔑 | ナレッジ登録 |
| GET | `/knowledge/items` | 🔑 | ナレッジ一覧 (`?status=pending` 等) |
| POST | `/knowledge/search` | 🔑 | RAGベクトル検索 |
| PUT | `/knowledge/items/{item_id}/status` | 🔑 | ステータス更新 |
| GET | `/knowledge/search/test` | 🔑 | 検索テスト |
| POST | `/knowledge/workflow/trigger` | 🔑 | E2Eワークフロートリガー |

---

## Automation `/api/automation`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/automation/status` | 🔑 | 自動運用ステータスサマリー |
| GET | `/api/automation/dashboard` | 🔑 | ダッシュボードスナップショット |
| GET | `/api/automation/reports/latest` | 🔑 | 最新サマリーレポート |
| POST | `/api/automation/workflow/run` | 👑 | E2Eワークフロー手動実行 |

---

## Notifications `/notifications` & `/api/notifications`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/notifications/push/subscribe` | 🔑 | プッシュ通知購読登録 |
| DELETE | `/notifications/push/unsubscribe` | 🔑 | プッシュ通知購読解除 |
| GET | `/notifications/push/vapid-key` | 🔓 | VAPID公開鍵取得 |
| POST | `/notifications/push/test` | 🔑 | プッシュ通知テスト送信 |
| GET | `/notifications/push/count` | 🔑 | 通知数取得 |

※ `/api/notifications/*` は同一エンドポイントへのエイリアス

---

## Data Feeds `/api/data-feeds`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/data-feeds/geo-risk` | 🔑 | 地政学リスク情報 |
| POST | `/api/data-feeds/geo-risk/refresh` | 👑 | 地政学リスク更新 |
| GET | `/api/data-feeds/news` | 🔑 | ニュースフィード |
| POST | `/api/data-feeds/news/refresh` | 👑 | ニュース更新 |
| GET | `/api/data-feeds/finance` | 🔑 | 金融データ |
| POST | `/api/data-feeds/finance/refresh` | 👑 | 金融データ更新 |
| POST | `/api/data-feeds/howl/review` | 🔑 | Howl AI レビュー |
| GET | `/api/data-feeds/agents` | 🔑 | エージェント一覧 |
| POST | `/api/data-feeds/agents/simulate` | 🔑 | エージェントシミュレーション |

---

## Reports `/api/reports`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/reports/monthly` | 🔑 | 月次レポート |

---

## Protocols

### Lido `/api/protocols/lido`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/protocols/lido/status` | 🔑 | Lido状態 |
| POST | `/api/protocols/lido/stake` | 🔑 | ステーク |
| POST | `/api/protocols/lido/withdraw` | 🔑 | 引き出し |
| GET | `/api/protocols/lido/apr` | 🔑 | APR取得 |

### Pendle `/api/protocols/pendle`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/protocols/pendle/markets` | 🔑 | マーケット一覧 |
| GET | `/api/protocols/pendle/market/{address}` | 🔑 | マーケット詳細 |
| POST | `/api/protocols/pendle/mint` | 🔑 | YT/PT mint |
| POST | `/api/protocols/pendle/redeem` | 🔑 | Redeem |
| GET | `/api/protocols/pendle/strategies` | 🔑 | 戦略比較 |

### Protocol Health `/api/protocols/health`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| GET | `/api/protocols/health` | 🔑 | 全プロトコルヘルス |
| GET | `/api/protocols/health/aave` | 🔑 | Aave ヘルス |
| GET | `/api/protocols/health/lido` | 🔑 | Lido ヘルス |
| GET | `/api/protocols/health/pendle` | 🔑 | Pendle ヘルス |

---

## DCA `/dca`

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/dca/execute` | 🔑 | DCA実行 |
| GET | `/dca/config` | 🔑 | DCA設定取得 |
| POST | `/dca/config` | 🔑 | DCA設定更新 |
| POST | `/dca/grid/execute` | 🔑 | グリッド取引実行 |
| GET | `/dca/grid/status` | 🔑 | グリッド状態 |
| GET | `/dca/grid/config` | 🔑 | グリッド設定 |

---

## その他

| Method | Path | 認証 | 説明 |
|--------|------|------|------|
| POST | `/octobot/signal` | 🔓 | OctoBotシグナル受信 |
| GET | `/api/safety-score` | 🔑 | 安全スコア（transparencyエイリアス） |
| POST | `/rss/fetch` | 👑 | RSSフィード手動取得 |
| GET | `/rss/feeds` | 🔑 | フィード一覧 |
| POST | `/webhook/tradingview` | 🔓 | TradingView Webhook受信 |
| POST | `/webhook/generic` | 🔓 | 汎用Webhook受信 |
| POST | `/api/hooks/slack-interaction` | 🔓 | Slack Interaction Webhook |
| GET | `/api/hooks/approval/{session_id}` | 🔓 | 承認セッション状態確認 |
| POST | `/notion/ingest` | 🔑 | Notion取り込み（旧API、非推奨） |

---

## よくある curl コマンド集

```bash
BASE=https://api.ultra-auto-trade.com
TOKEN="Bearer <JWT>"

# ヘルスチェック
curl -sf "${BASE}/health" | jq

# 最新AI判定
curl -sf -H "Authorization: ${TOKEN}" "${BASE}/api/ai/decisions/latest" | jq

# Aaveステータス
curl -sf -H "Authorization: ${TOKEN}" "${BASE}/api/aave/status" | jq

# Aave HF確認
curl -sf -H "Authorization: ${TOKEN}" "${BASE}/api/aave/health-factor" | jq

# 保留中の提案
curl -sf -H "Authorization: ${TOKEN}" "${BASE}/api/proposals/pending" | jq

# 提案承認
curl -sf -X POST -H "Authorization: ${TOKEN}" "${BASE}/api/proposals/{id}/approve" | jq

# 取引履歴
curl -sf -H "Authorization: ${TOKEN}" "${BASE}/api/transactions?limit=10" | jq

# ポートフォリオ
curl -sf -H "Authorization: ${TOKEN}" "${BASE}/api/portfolio/current" | jq

# 自動化ステータス
curl -sf -H "Authorization: ${TOKEN}" "${BASE}/api/automation/status" | jq
```
