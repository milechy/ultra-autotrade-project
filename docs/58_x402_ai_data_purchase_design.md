# x402 AI自律データ購入 設計ドキュメント

**文書番号:** docs/58  
**作成日:** 2026-06-15  
**ステータス:** Phase 0 (設計・スキーマ・純粋バリデータのみ。実決済未実装)  
**Tier:** B (本ドキュメント・スキーマ・バリデータ) / S (Phase 1以降の決済配線)

---

## 1. 統合方針

### 1.1 位置づけ

x402 を「AI 判断に必要な有料データの自律購入層」として Ultra AutoTrade に段階的に組み込む。

**実験的・段階的採用の明示:**  
x402 プロトコルはエコシステム (SDK / facilitator / 対応データプロバイダー) が成熟途上にある。
本設計は以下の原則で段階的に導入し、各フェーズを HUMAN-REVIEW ゲートで区切る:

- Phase 0 以降は**エコシステムの実態確認**を必須とする
- 推測による contract address / facilitator エンドポイントのハードコードを禁止する
- 実資金移動を伴う Phase 2/3 は**必ず人間承認**を経てから着手する

### 1.2 設計哲学

| 原則 | Ultra AutoTrade 既存実装との対応 |
|------|----------------------------------|
| Decimal-only (float 禁止) | Security Rules 11 / rebalance_schemas.py / workflow.py daily_limit |
| fail-open | data_feeds/ 各 feed: 取得失敗時は None 返却、context.py は degraded で継続 |
| 予算上限ハード制限 | workflow.py: `daily_limit = total_assets * Decimal("30") / Decimal("100")` と同思想 |
| emergency stop OR ロジック | Security Rules 6: 手動停止は決して上書きできない |
| 秘密鍵は env のみ | Security Rules 1: hardcode 禁止 / ログ禁止 |
| LLM 出力 JSON Schema 検証 | Security Rules 10: 購入意図は AI 生成でも Pydantic で検証必須 |

---

## 2. AI データ購入フローへの挿入点

### 2.1 既存の市場データ取得フロー

```
automation/ai_judgment_scheduler.py
    └── build_market_context()   [data_feeds/context.py]
            ├── get_cached_geo_risk()     [geopolitical.py]
            ├── get_cached_finance()      [finance_feed.py]
            ├── get_cached_news()         [news_feed.py]
            └── get_cached_mmt_data()     [mmt_feed.py]
```

`build_market_context()` は各 feed を並列キャッシュから読み取り、失敗時は degraded context で継続する
(ai_judgment_scheduler.py:632: `using degraded context`)。

### 2.2 x402 有料データの将来挿入点

Phase 1 以降で `build_market_context()` に x402 経由の有料ソースを**オプション**として追加する:

```python
# Phase 1 以降 (実装例 — 現時点では未実装):
# data_feeds/context.py::build_market_context() 内

# 既存無料フィードと同等の fail-open 設計
# 予算超過 / facilitator 不通 / 402 取得失敗時は None フォールバック
premium_sentiment: Optional[PremiumSentimentData] = None
if x402_enabled and x402_budget_ok:
    try:
        premium_sentiment = await x402_client.fetch(intent)
    except Exception:
        pass  # fail-open: 有料データ取得失敗でも AI 判断は継続
```

**設計上の制約:**
- 有料データの欠落は HOLD bias に倒すことで安全側に倒す
- 有料データなしでも AI 判断フロー全体は継続可能な設計とする
- 購入意図は Pydantic (`X402PurchaseIntent`) で型検証してから使用する

---

## 3. 決済ポリシー / 予算上限スキーマ

### 3.1 スキーマ構成 (Phase 0 実装済み)

| スキーマ | ファイル | 役割 |
|----------|---------|------|
| `X402PaymentToken` | schemas.py | 決済トークン種別 (symbol のみ / contract address 不持) |
| `X402PurchaseIntent` | schemas.py | 購入意図 (read-only / HTTP・署名含まず) |
| `X402BudgetPolicy` | schemas.py | 予算ポリシー (Decimal-only) |

### 3.2 予算設計思想

`workflow.py` の安全装置と同等の多層制限:

```
workflow.py 既存:
  HARD_STOP   HF < Decimal("1.6")                  → 即停止
  daily_limit = total_assets * Decimal("30") / 100  → 超過で取引停止

x402 対応 (X402BudgetPolicy):
  max_per_request_usd  1リクエスト上限 (Decimal)   → 超過で購入拒否
  daily_budget_usd     日次予算上限 (Decimal)       → 超過で購入拒否 (daily_limit_reached 相当)
```

**Decimal 境界値の扱い:**
- `amount_usd <= max_per_request_usd` (= 上限ちょうどは許容)
- `spent_today_usd + amount_usd <= daily_budget_usd` (= 上限ちょうどは許容)
- float 演算の誤差を排除するため全計算を `Decimal` で実施

### 3.3 pure function バリデータ (Phase 0 実装済み)

`validators.py` に外部 I/O・blockchain に依存しない純粋関数群を実装:

| 関数 | 検証内容 | 失敗時 |
|------|---------|--------|
| `validate_amount_positive` | amount_usd > 0 | ValueError |
| `validate_within_per_request_limit` | amount_usd <= max_per_request_usd | ValueError |
| `validate_within_daily_budget` | spent + amount <= daily_budget_usd | ValueError |
| `validate_token_allowed` | token in allowed_tokens | ValueError |
| `validate_purchase_intent` | 上記 AND 集約 | `(False, reason)` |

`validate_purchase_intent` の戻り値形式は `workflow.py` の `(False, "daily_limit_reached")` に準拠。

---

## 4. x402 facilitator / SDK 【要確認】列挙

> **注意:** 以下は Phase 1 以降の実装前に **実際のドキュメント・SDK・エコシステム状態を調査して確認**すること。
> 推測確定禁止。本セクションの情報は記述時点 (2026-06-15) での調査状態を示す。

### (i) x402 SDK / 言語サポート 【要確認】

- x402 は HTTP 402 Payment Required を利用した決済プロトコル (Coinbase / CDP が推進)
- 公式リポジトリ: `github.com/coinbase/x402` (Python SDK の有無・成熟度を実調査すること)
- Python SDK が未整備の場合: `httpx` + 手動 header 実装が必要 (Phase 1 HUMAN-REVIEW スコープ)

### (ii) facilitator (自前 / 第三者) 【要確認】

- x402 は facilitator が payment header を検証し、データプロバイダーに通知する中継者
- 第三者 facilitator (Coinbase 提供等) の利用可否・料金・SLA を確認すること
- 自前 facilitator 運用は追加インフラコスト・秘密鍵管理が必要 (HUMAN-REVIEW スコープ)
- **決定前に実際の facilitator エンドポイント URL を確認すること (推測ハードコード禁止)**

### (iii) 対応チェーン 【要確認】

- Ultra AutoTrade 既存: Base Mainnet (production) / Base Sepolia (staging)
  - `backend/app/aave/client.py`: `_POOL_ADDRESS_BASE_MAINNET`, `_POOL_ADDRESS_BASE_SEPOLIA`
- x402 の Base Mainnet 対応状況・必要 contract を実調査すること
- 他チェーン (Polygon / Arbitrum) の対応は優先度低 (既存 Aave 設定に合わせる)

### (iv) 決済トークン (contract address) 【要確認 / HUMAN-REVIEW】

- USDC (Base Mainnet): `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` (参考値 — **実調査で確認すること**)
- USDT (Base Mainnet): 要確認
- **contract address は schemas.py に持たせない** (Phase 0 設計決定):
  - チェーン・環境 (mainnet/testnet) で異なる
  - env 変数または facilitator 設定で解決する (Phase 2 HUMAN-REVIEW スコープ)
  - hardcode は Security Rules 1 違反の懸念があるため HUMAN-REVIEW を必須とする

### (v) payment header 正式スキーマ 【要確認 / HUMAN-REVIEW】

- x402 payment header の正式仕様 (EIP / Coinbase 仕様書) を確認すること
- `X-Payment` ヘッダーの構造・署名方式・エンコード形式は実装前に仕様書を確認
- **本スライス (Phase 0) では payment header を一切実装しない**

### (vi) 既存ウォレット / 鍵管理との統合点 【HUMAN-REVIEW】

- 既存: `PRIVATE_KEY` (env のみ) → `web3.py` → Aave V3 操作
- x402 決済用ウォレット: 同一キーの使用可否、または専用ウォレットの要否を検討
- **鍵管理の設計変更は HUMAN-REVIEW 必須** (Security Rules 1 / 7)
- staging (`AAVE_NETWORK=base_sepolia`) と production (`AAVE_NETWORK=base`) で**物理的に異なるキー**を使用すること (Security Rules 7)

---

## 5. 段階実装計画

| Phase | 内容 | Tier | 承認要否 | 完了条件 |
|-------|------|------|---------|---------|
| **Phase 0** (本スライス) | 設計ドキュメント + 購入意図スキーマ + 純粋バリデータ + pytest | B | 不要 (自動進行) | ruff / mypy / pytest 全通過 |
| **Phase 1** | read-only 402 検出のみ (dry-run) — facilitator に通知しない / 実支払いなし | B→A | HUMAN-REVIEW (HTTP 実装) | staging でのドライラン動作確認 |
| **Phase 2** | facilitator 通信 (Base Sepolia testnet) — USDC testnet で実際に購入 | A | HUMAN-REVIEW 必須 | testnet tx 成功確認 / 予算上限動作確認 |
| **Phase 3** | 本番決済 (Base Mainnet) — 実資金移動 | S | **HUMAN-REVIEW 必須** (予算配線 / cooldown / emergency stop OR 配線 / workflow.py 統合) | 本番 wallet 残高変動確認 / 日次予算上限 Decimal 検証 |

### Phase 1 着手前チェックリスト (HUMAN-REVIEW)

- [ ] x402 Python SDK または httpx 実装方針決定
- [ ] facilitator エンドポイント URL 実確認 (推測禁止)
- [ ] payment header 仕様確認 (EIP / Coinbase ドキュメント)
- [ ] HTTP 実装は `backend/app/data_feeds/x402/` 内に隔離
- [ ] `main.py` への配線は Tier S として別 PR

### Phase 3 着手前チェックリスト (HUMAN-REVIEW 必須)

- [ ] 日次予算上限を `X402BudgetPolicy` + `workflow.py` の安全装置と接続
- [ ] emergency stop OR ロジック配線 (手動停止が x402 購入を上書きしないことを確認)
- [ ] cooldown 実装 (Security Rules 5: Aave 10分 cooldown との兼ね合い)
- [ ] staging / production でキーを物理分離していることを確認 (Security Rules 7)
- [ ] 本番ウォレットへの資金移動前に Health Factor 確認 (Security Rules 2: HF < 1.6 HARD_STOP)

---

## 6. 安全境界 (Phase 0 現時点)

Phase 0 実装 (`schemas.py`, `validators.py`) は以下を**一切含まない**:

- HTTP リクエスト (`httpx`, `requests`, `aiohttp`)
- blockchain 操作 (`web3`, `eth_account`)
- 秘密鍵アクセス (env 参照なし)
- facilitator 通信
- payment header 生成・検証
- ウォレット署名
- `backend/app/main.py` への配線 (router 登録なし)

grep 確認コマンド:

```bash
grep -rniIE "private|secret|sign|httpx|requests\.|web3|wallet|payment.?header|facilitator" \
  backend/app/data_feeds/x402/*.py | grep -viE "#|\"\"\"|要確認|description|docstring"
# 期待: 出力なし (安全境界 OK)

grep -nE "x402|include_router" backend/app/main.py
# 期待: 出力なし (main.py 未配線 OK)
```

---

## 7. 参照ファイル

| ファイル | 参照目的 |
|---------|---------|
| `backend/app/data_feeds/x402/schemas.py` | 購入意図・予算ポリシー Pydantic スキーマ |
| `backend/app/data_feeds/x402/validators.py` | 純粋バリデータ群 |
| `backend/tests/data_feeds/x402/test_x402_validators.py` | バリデータテスト |
| `backend/app/aave/rebalance_schemas.py` | Decimal パターン参照元 |
| `backend/app/automation/workflow.py` | daily_limit / HF HARD_STOP 参照元 |
| `backend/app/data_feeds/context.py` | build_market_context() / fail-open 参照元 |
| `docs/13_security_design.md` | Security Rules 全文 |
