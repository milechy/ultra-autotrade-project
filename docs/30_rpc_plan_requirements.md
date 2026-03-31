# RPC プロバイダー要件

> 最終更新: 2026-03-31  
> メインネット移行時の有料RPCプラン選定のための調査・見積もりドキュメント。

---

## 現在のRPC使用パターン

### 呼び出しモジュールと使用RPCメソッド

#### `backend/app/aave/client.py` — Web3AaveClient（メイン実装）

| メソッド | 使用RPCメソッド | 用途 |
|---|---|---|
| `get_health_factor()` | `eth_call` | Aave Pool.getUserAccountData() |
| `get_account_data()` | `eth_call` | Aave Pool.getUserAccountData() |
| `deposit()` | `eth_call` × 2 | ERC20.decimals(), ERC20.balanceOf() |
| | `eth_getTransactionCount` × 2–3 | approve + supply の nonce 取得 |
| | `eth_gasPrice` × 2–3 | ガス価格取得 |
| | `eth_estimateGas` × 2–3 | gas 見積もり（with buffer） |
| | `eth_sendRawTransaction` × 2 | approve + supply 送信 |
| | `eth_getTransactionReceipt` × 2 | receipt ポーリング |
| `withdraw()` | `eth_call` × 2 | ERC20.decimals(), ERC20.balanceOf() |
| | `eth_getTransactionCount` × 2 | withdraw の nonce 取得 |
| | `eth_gasPrice` × 2 | ガス価格取得 |
| | `eth_estimateGas` × 2 | gas 見積もり |
| | `eth_sendRawTransaction` × 1 | withdraw 送信 |
| | `eth_getTransactionReceipt` × 1 | receipt ポーリング |

#### `backend/app/aave/gas_estimator.py`

| メソッド | 使用RPCメソッド | 用途 |
|---|---|---|
| `estimate_gas_with_buffer()` | `eth_estimateGas` | ガス見積もり + 20% バッファ |
| `get_gas_price()` | `eth_gasPrice` | 現在のガス価格 |

#### `backend/app/aave/rpc_provider.py` — フェイルオーバー管理

| メソッド | 使用RPCメソッド | 用途 |
|---|---|---|
| `_is_connected()` | `eth_blockNumber` | 接続チェック（エラー時のフェイルオーバー） |

#### `backend/app/automation/background_tasks.py` — 監視ループ

| 処理 | 使用RPCメソッド | 間隔 |
|---|---|---|
| HF監視ループ | `eth_call` (getUserAccountData) | 60秒ごと（デフォルト） |

#### `backend/app/automation/rebalance_job.py` — リバランスチェック

| 処理 | 使用RPCメソッド | 間隔 |
|---|---|---|
| リバランス要否チェック | （HFチェック経由） | 14400秒 = 4時間ごと |
| リバランス実行時 | deposit() or withdraw() 一式 | 必要時のみ |

---

## 日次リクエスト見積もり

### 前提条件
- テスター: 10人
- HF監視間隔: 60秒（デフォルト、`MONITORING_INTERVAL_SECONDS`）
- リバランスチェック間隔: 4時間（`REBALANCE_CHECK_INTERVAL_SECONDS = 14400`）
- リバランス実行頻度: 1–2回/日（市況次第）
- AI判定: 6回/日（4時間ごと）

### リクエスト内訳

| 処理 | RPCメソッド | 頻度 | リクエスト数/日 |
|---|---|---|---|
| HF監視（毎分） | `eth_call` × 1 | 1440回/日 | **1,440** |
| リバランスチェック（4時間ごと、アクションなし） | `eth_call` × 1 | 6回/日 | 6 |
| リバランス実行（deposit/withdraw 1回） | `eth_call`, `eth_getTransactionCount`, `eth_gasPrice`, `eth_estimateGas`, `eth_sendRawTransaction`, `eth_getTransactionReceipt` | ~15コール/回 × 2回 | **30** |
| 接続チェック（フェイルオーバー時） | `eth_blockNumber` | 断続的 | ~50 |
| テスター操作（手動操作含む） | 各種 | 10人 × 5操作 | **50** |
| **合計** | | | **~1,576** |

### 結論
**通常運用時: 約1,500〜2,000 RPC requests/day**

> Note: HF監視間隔を5分（300秒）に緩和した場合、監視分は 288/日 となり、合計 ~400–500 req/day に削減可能。

---

## プロバイダー比較（2026年時点）

> **重要**: 以下は概算です。最新の料金・制限は必ず各プロバイダーの公式サイトで確認してください。

### Alchemy

| プラン | 月額 | Compute Units/月 | スループット | 日次上限 |
|---|---|---|---|---|
| Free | $0 | 300M CU | 330 CU/秒 | ~100K req |
| Growth | $49 | 400M CU | 660 CU/秒 | 制限なし |
| Scale | $199 | 1.5B CU | 1,500 CU/秒 | 制限なし |

※ `eth_call` = 26 CU, `eth_sendRawTransaction` = 250 CU, `eth_getTransactionReceipt` = 15 CU

### Infura

| プラン | 月額 | リクエスト/日 | レート制限 |
|---|---|---|---|
| Free | $0 | 100K | 10 req/秒 |
| Core | $50 | 100K | 100 req/秒 |
| Growth | $225 | 制限なし | 500 req/秒 |

### QuickNode

| プラン | 月額 | リクエスト/月 | レート制限 |
|---|---|---|---|
| Free | $0 | 10M | 10 req/秒 |
| Build | $49 | 100M | 100 req/秒 |
| Scale | $299 | 制限なし | 200 req/秒 |

---

## 推奨構成

### テスター10人規模（現フェーズ）

| 役割 | プロバイダー | プラン | 月額 |
|---|---|---|---|
| プライマリ RPC | Alchemy | Growth | $49 |
| セカンダリ RPC（フェイルオーバー） | Infura | Core | $50 |
| **合計** | | | **$99/月** |

- Alchemy Growth の 400M CU/月は 1,600 req/日換算で余裕あり
- Infura Core はフェイルオーバー専用（通常は使わない）

### 本番100人規模

| 役割 | プロバイダー | プラン | 月額 |
|---|---|---|---|
| プライマリ RPC | Alchemy | Scale | $199 |
| セカンダリ RPC（フェイルオーバー） | Infura | Growth | $225 |
| **合計** | | | **$424/月** |

> HF監視間隔を 300秒（5分）に緩和すると、Alchemy Growth でも100人規模に対応できる可能性がある。

---

## 環境変数設定

`.env.staging` / `.env.production` での設定例:

```bash
# =============================================================================
# Aave V3 RPC — メインネット（Alchemy プライマリ + Infura セカンダリ）
# =============================================================================

# プライマリ RPC（Alchemy）
# Arbitrum One: https://dashboard.alchemy.com/ でプロジェクト作成後に取得
AAVE_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}

# セカンダリ RPC（Infura フェイルオーバー用）
# Infura: https://infura.io/ でプロジェクト作成後に取得
AAVE_RPC_URL_SECONDARY=https://arbitrum-mainnet.infura.io/v3/{INFURA_PROJECT_ID}

# Base Mainnet（将来対応時）
# AAVE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}
# AAVE_RPC_URL_SECONDARY=https://base-mainnet.infura.io/v3/{INFURA_PROJECT_ID}
```

---

## レート制限監視

現状の `rpc_provider.py` は HTTP 接続失敗時にフェイルオーバーする。
ただし 429 (Rate Limit) エラーは接続成功扱いになるため、追加監視が推奨される。

### 推奨対応（将来タスク）

1. **429 エラーログ監視**: `rpc_provider.py` で `HTTPError(429)` をキャッチして Slack アラート
2. **Compute Unit 使用量監視**: Alchemy ダッシュボードの Webhook で月次 CU 使用率をチェック
3. **HF監視間隔の動的調整**: 負荷が高い時間帯は `MONITORING_INTERVAL_SECONDS` を 120〜300 秒に緩和

---

## 関連ファイル

- `backend/app/aave/rpc_provider.py` — フェイルオーバーロジック実装済み
- `backend/app/aave/client.py` — Web3AaveClient（全RPC呼び出し）
- `backend/app/aave/gas_estimator.py` — ガス見積もり
- `backend/app/automation/background_tasks.py` — HF監視ループ（60秒デフォルト）
- `backend/app/automation/rebalance_job.py` — リバランスチェック（4時間ごと）
- `.env.staging.example` — 環境変数テンプレート
