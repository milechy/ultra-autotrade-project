# 07_aave_operation_logic.md  
Ultra AutoTrade – Aave運用ロジック（リスク管理追加）

---

# 1. 基本行動

BUY → deposit  
SELL → withdraw  
HOLD → 何もしない  

---

# 2. リスク管理（重要）

## 2.1 Health Factor
```
HF < 1.8 → 警告  
HF < 1.6 → 運用停止 + 通知  
```

## 2.2 投資上限
```
1回の投資額：総資金の10%  
1日の投資上限：総資金の30%
```

## 2.3 自動停止条件
- ガスエラー2回連続  
- Aave応答なし3回  
- 資産変動 > 20%/日  

---

# 3. ガス管理
- ガス高騰時は自動待機  
- 5分後に再実行  

---

# 4. 連続トレード制限
- 10分以内の連続取引は禁止  


---

## 5. ステージング環境（テストネット）での運用ルール

本番運用前に、Aave との連携は **テストネット（staging）** で検証する。  
Ultra AutoTrade では、Aave 関連の設定値は `backend/app/aave/config.py` から  
次の環境変数で制御される。

## 5.1 ステージング環境の基本方針

- ステージングでは **テストネットのみ** を使用する
  - 例: `polygon-mumbai` などのテストネット
- ウォレットは **テスト用アドレス** を利用し、本番資金とは完全に分離する
- 取引金額は極小（検証に十分な最小額）に抑える
- Health Factor / クールダウンなどのリスクパラメータは  
  本番と同等か、それ以上に保守的な値を設定する

## 5.2 Aave 関連環境変数（抜粋）

`backend/app/aave/config.py` では、次の環境変数を使用する:

| 環境変数名                    | 役割                                        | ステージングの推奨例                          |
|------------------------------|---------------------------------------------|-----------------------------------------------|
| `AAVE_NETWORK`               | 利用するネットワーク名                      | `polygon-mumbai` などテストネット名          |
| `AAVE_RPC_URL`               | 対応ネットワークの RPC エンドポイント      | テストネット RPC の URL                       |
| `AAVE_DEFAULT_ASSET_SYMBOL`  | デフォルトで扱う資産シンボル               | 例: `USDC`（テストネット上のトークン）        |
| `AAVE_MAX_SINGLE_TRADE_USD`  | 1 回のトレードで許容する最大 USD 相当額    | 本番よりさらに小さく（例: `1`〜`10` USD）     |
| `AAVE_MIN_HEALTH_FACTOR`     | 最小許容 Health Factor                      | 本番と同等以上（例: `1.6` など）              |
| `AAVE_TRADE_COOLDOWN_SECONDS`| 連続トレードのクールダウン秒数             | 本番と同等以上（例: `600` 秒）                |

## 5.3 `.env.staging` の設定例（Aave テストネット）

```bash
# Aave (staging / testnet)
AAVE_NETWORK=polygon-mumbai
AAVE_RPC_URL=https://polygon-mumbai.infura.io/v3/your_project_id
AAVE_DEFAULT_ASSET_SYMBOL=USDC
AAVE_MAX_SINGLE_TRADE_USD=5
AAVE_MIN_HEALTH_FACTOR=1.6
AAVE_TRADE_COOLDOWN_SECONDS=600

※ 上記はあくまで例であり、実際には利用するテストネット・RPC プロバイダに応じて変更する。

## 5.4 緊急停止フラグ・ロールバックとの関係
- テストネットであっても、異常挙動が発生した場合は
  - 緊急停止フラグを立てる（MonitoringService 経由）
  - 必要に応じて 15_rollback_procedures.md に従いロールバック手順を実施する
- 本番への移行前に、staging 環境で
  - 緊急停止フロー
  - ロールバックフロー
  - の動作確認を行うことが望ましい。
## 6. モード別実行ルール（2026-03-23追加）

### 6.1 execution_policy による分岐

| execution_policy | Aave操作 | 提案作成 | 承認 |
|-----------------|---------|---------|------|
| `auto_execute` | 即時実行 | なし | 不要 |
| `require_approval` | 承認後実行 | 作成（TTL: 1時間） | 必要 |
| `proposal_only` | 実行しない | 作成のみ | 不要 |

### 6.2 ガス代チェック（auto_execute時）

- 推定利益（supply APY × amount × 期間） > 推定ガス代 の場合のみ実行
- ガス代はトランザクション送信前に `eth_estimateGas` で取得

### 6.3 緊急時オーバーライド

- HF < 1.6 の場合: `execution_policy` に関わらず即時 `auto_execute`
- 緊急時の操作は LINE で `notify_hf_protection()` を呼び出して通知
