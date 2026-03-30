# セキュリティレビュー

**日付:** 2026-03-30
**対象ブランチ:** dev
**対象ファイル:**
- `backend/app/aave/` 配下の全 .py ファイル
- `backend/app/automation/monitoring_service.py`
- `backend/app/auth/` 配下の全 .py ファイル

**根拠ドキュメント:** `docs/13_security_design.md`

---

## チェック結果サマリ

| # | チェック項目 | 結果 | 備考 |
|---|-------------|------|------|
| 1 | 秘密鍵が環境変数のみで管理 | ✅ 確認済み | |
| 2 | HF < 1.6 で自動 HARD_STOP | ✅ 確認済み | |
| 3 | 1回取引 ≤ 総資金の10% | ⚠️ 部分準拠 | 固定USD上限、要注意 |
| 4 | 日次取引 ≤ 総資金の30% | ⚠️ 部分準拠 | 回数制限、要注意 |
| 5 | クールダウン（10分）実装 | ✅ 確認済み | |
| 6 | 緊急停止 OR 論理 | ✅ 確認済み | |
| 7 | ログに秘密情報なし | ✅ 確認済み | |
| 8 | LLM 出力の JSON 検証 | ✅ 確認済み | フォーマルスキーマ検証は将来推奨 |
| 9 | 金融計算は Decimal 型 | ✅ 確認済み | ccxt 境界のみ float（許容範囲） |
| 10 | SQLインジェクション対策 | ✅ 確認済み | |

---

## 詳細確認結果

### 1. 秘密鍵が環境変数のみで管理されているか ✅

**確認箇所:**

- `aave/config.py:137` — `wallet_private_key = get_env("AAVE_WALLET_PRIVATE_KEY", required=False)`
- `auth/service.py:35` — `SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key-change-in-production")`
  → `validate_secret_key()` が staging/production で弱いキーを拒否（`service.py:55-78`）
- `aave/client.py:361` — `Account.from_key(settings.wallet_private_key)` — 環境変数から受け取るのみ

ハードコードされた秘密鍵・API キーは存在しない。
テストネット用コントラクトアドレス（`_POOL_ADDRESS_SEPOLIA` 等）は秘密情報ではないため問題なし。

---

### 2. Health Factor < 1.6 で自動 HARD_STOP が発動するか ✅

**確認箇所:**

- `automation/monitoring_service.py:65` — `healthfactor_emergency_threshold: Decimal = Decimal("1.6")`
- `automation/monitoring_service.py:406-429` — HF < 1.6 で `_trading_paused = True`、`hf_triggered_emergency = True` をセット
- `automation/monitoring_service.py:220-224` — state.json に `mode = HARD_STOP` を書き込み
- `aave/service.py:262-279` — `MonitoringService.is_trading_allowed()` が False の場合 NOOP 強制
- `aave/service.py:144-153` — `_decide_operation()` で HF < `min_health_factor` かつ BUY → NOOP

HF < 1.6 の検知から取引停止まで、3 層の防御が実装されている。

---

### 3. 1回の投資額が総資金の10%以下に制限されているか ⚠️ 部分準拠

**確認箇所:**

- `aave/config.py:99-102` — `max_single_trade_usd: Decimal = 100.0`（固定 USD 上限）
- `aave/service.py:105-107` — `_normalize_amount()` で上限にクリップ
- `exchange/service.py:135-153` — `max_order_usd` 超過で SKIPPED

**現状:** 固定額 `$100 USD` の上限で制御。Security Rules §3 は「総資金の10%」（パーセンテージ）を要求しているが、PoC 段階では固定額での代替実装。

**リスク評価:** 低（$100 上限は保守的な固定値。本番移行時に総資金連動型に更新を推奨）

**推奨アクション（本番移行前）:** `get_account_data()` から `total_collateral_usd` を取得し、動的に10%上限を計算する仕組みを追加する。

---

### 4. 1日の投資上限が総資金の30%以下に制限されているか ⚠️ 部分準拠

**確認箇所:**

- `exchange/service.py:89-108` — `daily_trade_limit`（回数制限、デフォルト10回）超過で SKIPPED
- `.env.production.example` — `EXCHANGE_DAILY_TRADE_LIMIT=10`

**現状:** 回数ベースの制限（10回/日）。Security Rules §4 は「総資金の30%」（パーセンテージ）を要求しているが、PoC 段階では回数での代替実装。1回の上限が $100 の場合、最大 $1000/日 が上限となる。

**リスク評価:** 低（PoC 段階では妥当な代替策。本番移行時に累積取引額ベースに更新を推奨）

**推奨アクション（本番移行前）:** 1日の累積取引額を記録し、総担保資産の30%を超えたら SKIPPED にする。

---

### 5. クールダウン（10分）が実装されているか ✅

**確認箇所:**

- `aave/config.py:111-114` — `trade_cooldown_seconds: int = 600`（デフォルト10分）
- `aave/service.py:88-93` — `_is_in_cooldown()` — クールダウン窓内にトレードがあれば True
- `aave/service.py:139-143` — クールダウン中は NOOP を返す
- `exchange/service.py:111-132` — 経過時間 < `cooldown_seconds` で SKIPPED

Aave 側・取引所側の両方でクールダウンが実装されている。

---

### 6. 緊急停止フラグが OR 論理で実装されているか ✅

**確認箇所:**

- `automation/monitoring_service.py:231-232`:
  ```python
  existing_emergency = current.emergency_stop
  final_emergency_stop = existing_emergency or hf_triggered_emergency
  ```
- `automation/monitoring_service.py:609-616` — `clear_emergency_stop()` のみが `emergency_stop=False` に戻せる
- `aave/service.py:204-215` — `state.emergency_stop` が True の場合、HF 回復後も NOOP を強制
- コメント: 「False に戻すのは `clear_emergency_stop()` 呼び出し時のみ」（`monitoring_service.py:616`）

手動緊急停止は自動 HF 回復で上書きされない。OR 条件が正しく実装されている。

---

### 7. ログに秘密情報（トークン、APIキー、秘密鍵）が含まれていないか ✅

**確認箇所:**

- `aave/client.py:376-379` — プール初期化ログ: `pool_address[:6]...pool_address[-4:]`（先頭6・末尾4文字）
- `aave/client.py:530-537` — deposit ログ: `asset_address[:6]...[-4:]`、`wallet_address[:6]...[-4:]`（秘密鍵は含まない）
- `aave/client.py:337` — RPC URL: `effective_rpc_url[:20]...`（URLの先頭20文字のみ）
- `auth/service.py:257` — ユーザー作成ログ: email のみ（パスワードハッシュは含まない）
- `auth/service.py:403` — ウォレットユーザーログ: `wallet_address[:10]`（先頭10文字のみ）
- 全 logger 呼び出しでトークン・秘密鍵をそのまま出力している箇所なし

Security Rules §8「先頭6文字＋末尾4文字のみ許可」に準拠している。

---

### 8. LLM 出力が JSON Schema 検証されているか ✅

**確認箇所:**

- `ai/service.py:478-510` — `_parse_llm_response()`:
  - `json.loads(text)` でパース
  - `action` が BUY/SELL/HOLD 以外 → `"HOLD"` に正規化
  - `confidence` を `max(0, min(100, int(...)))` でクランプ
  - `json.JSONDecodeError`, `ValueError`, `KeyError`, `TypeError` → HOLD（fail-closed）

Security Rules §10「parse failure → HOLD」は実装されている。
ライブラリ（`jsonschema` 等）による形式的な JSON Schema 検証は未導入。現状のシンプルなスキーマでは機能的に同等だが、スキーマが複雑化した場合は `jsonschema.validate()` の導入を推奨。

---

### 9. 金融計算が Decimal 型で行われているか ✅

**確認箇所:**

- `aave/client.py:422` — `hf = Decimal(hf_raw) / Decimal(10**18)` — ✅
- `aave/client.py:454-468` — AccountData フィールド全て `Decimal` — ✅
- `aave/service.py` — `normalized_amount: Decimal`、全演算 Decimal — ✅
- `exchange/service.py:172` — `price = Decimal(str(ticker["last"]))` — ✅

**ccxt API 境界での float 変換（許容範囲）:**
- `exchange/service.py:176-178` — `quantity = float(request.amount_usd / price)`
  ccxt ライブラリが `float` を要求するため、API 境界でのみ変換している。Decimal で計算してから変換しており、計算精度への影響なし。これは許容される実装パターン。

---

### 10. SQLインジェクション対策（SQLAlchemy ORM 使用）✅

**確認箇所:**

- `auth/service.py:171` — `db.query(User).filter(User.email == email).first()` — ORM ✅
- `auth/service.py:175` — `db.query(User).filter(User.id == user_id).first()` — ORM ✅
- `auth/service.py:179` — `db.query(User).filter(User.username == username).first()` — ORM ✅
- `auth/service.py:340` — `db.query(User).filter(User.wallet_address == wallet_address.lower()).first()` — ORM ✅

全クエリが SQLAlchemy ORM 経由。生 SQL 文字列の組み立ては存在しない。

---

## 本番移行前の推奨対応（Critical ではないが推奨）

### P2: 取引額の総資金連動化（Rules §3, §4）

現状はリスクが低い（$100/回上限は保守的）が、本番で大きな資金を運用する前に対応が必要。

```python
# aave/service.py の execute_rebalance() に追加（イメージ）
account_data = self._client.get_account_data(wallet_address)
max_10pct = account_data.total_collateral_usd * Decimal("0.10")
normalized_amount = min(normalized_amount, max_10pct)
```

### P3: JSON Schema ライブラリの導入（Rule §10）

AI スキーマが複雑化した際の備えとして。現状は機能的に問題なし。

---

## 修正内容

本レビューで発見された問題のうち、即時修正が必要なもの: **なし**

⚠️ 部分準拠（Rules §3, §4）は PoC フェーズの設計判断であり、本番移行前に対応が必要。
