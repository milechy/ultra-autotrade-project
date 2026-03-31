# Stream H セキュリティ監査レポート

**対象プロジェクト:** Ultra AutoTrade
**監査基準:** docs/13_security_design.md
**監査日:** 2026-03-11
**監査者:** Stream H 自動セキュリティレビュー
**テストスイート:** `backend/tests/test_security_review.py` (41 tests, 全 PASS)

---

## 1. 監査手法

本レポートは以下の方法でセキュリティ要件の実装状況を検証した。

1. **静的解析 (AST)** — Python ソースを AST でパースし、ハードコードされたシークレット候補を抽出
2. **コードパターン照合** — セキュリティ要件（ログマスク、OR ロジック等）の実装パターンをソースで確認
3. **自動テスト** — pytest を用いた動作検証（41 テスト全 PASS）
4. **依存チェーン追跡** — `main.py` → `startup` イベント → `validate_secret_key()` 呼び出しの有無を確認

---

## 2. セキュリティルール別評価

### ルール 1: 秘密鍵/API キーのハードコード禁止

| 評価 | PASS |
|------|------|
| 根拠 | 全設定ファイルが `get_env()` / `os.getenv()` を使用して環境変数から値を取得している |

**確認済みファイル:**
- `backend/app/aave/config.py` — `get_env()` のみ使用
- `backend/app/exchange/config.py` — `get_env()` のみ使用
- `backend/app/ai/config.py` — `get_env()` のみ使用
- `backend/app/notifications/config.py` — `get_env()` のみ使用

**例外 (意図的なデフォルト値):**
- `auth/service.py:28`: `"development-secret-key-change-in-production"` は JWT の開発環境デフォルト値。本番では `validate_secret_key()` によって拒否される（ルール 5 参照）。

---

### ルール 2: ログへの秘密鍵/トークン出力禁止（先頭 6 + 末尾 4 文字マスク）

| 評価 | PASS |
|------|------|
| 根拠 | `aave/client.py` に `wallet_address[:6]` と `wallet_address[-4:]` のマスクパターンが実装されている |

**実装箇所:**
- `backend/app/aave/client.py:398-399` — `wallet_address[:6]` / `wallet_address[-4:]`
- `backend/app/aave/client.py:467-471` — `asset_address[:6]` / `wallet_address[:6]` / `wallet_address[-4:]`
- `backend/app/aave/client.py:618-622` — 同上（withdraw ログ）

`settings.private_key` や `wallet_private_key` をそのままログ出力するコードは存在しない。

---

### ルール 3: Health Factor < 1.6 → HARD_STOP (デュアルレイヤー)

| 評価 | PASS |
|------|------|
| 根拠 | クライアント層と監視層の 2 箇所で独立して実装されている |

**レイヤー 1: MonitoringService (`monitoring_service.py:380`)**
```python
if value < self._hf_emergency_threshold:   # Decimal("1.6")
    level = AlertLevel.EMERGENCY
    is_emergency = True
    self._trading_paused = True
```

**レイヤー 2: AaveService (`service.py:286`)**
```python
if hf_status.is_emergency and action == TradeAction.BUY:
    return AaveOperationResult(... status=SKIPPED ...)
```

**さらに `_sync_state_file` でモード遷移:**
- HF >= 1.8: `NORMAL`
- 1.6 <= HF < 1.8: `SAFE_MODE`
- HF < 1.6: `HARD_STOP`

テスト: `TestHealthFactorHardStop` (5 テスト全 PASS)

---

### ルール 4: 緊急停止フラグの OR ロジック（手動停止は自動上書き不可）

| 評価 | PASS |
|------|------|
| 根拠 | `_sync_state_file` が `existing_emergency OR hf_triggered_emergency` で更新する |

**実装箇所 (`monitoring_service.py:205-206`):**
```python
existing_emergency = current.emergency_stop
final_emergency_stop = existing_emergency or hf_triggered_emergency
```

この設計により:
- オペレーターが `emergency_stop=True` をセットしても、安全な HF が記録されても `False` に上書きされない
- `False` に戻すのは `clear_emergency_stop()` の明示的呼び出しのみ

テスト: `TestEmergencyStopOrLogic` (4 テスト全 PASS)

---

### ルール 5: JWT 弱いシークレットキーの本番環境での禁止

| 評価 | PASS (実装あり) / WARN (startup 呼び出し未確認) |
|------|------|
| 根拠 | `validate_secret_key()` は実装済みだが、`main.py` の startup イベントから呼ばれていない |

**実装 (`auth/service.py:48-71`):**
- `APP_ENV` が `production` または `staging` の場合、弱いキー → `RuntimeError`
- `_WEAK_SECRET_KEYS` セット: `"development-secret-key-change-in-production"`, `"secret"`, `"changeme"`, `"password"`, `"test"`, `""`
- 32 文字未満のキーも拒否

**WARN: `main.py` で `validate_secret_key()` が startup 時に呼ばれていない**

`main.py` の `startup_database` / `startup_event` いずれにも `AuthService.validate_secret_key()` の呼び出しが存在しない。これは、本番デプロイ時に弱いキーを使っても起動時点でエラーにならないことを意味する。

**推奨対処:**
```python
# main.py の create_app() または startup イベントに追加
from app.auth.service import AuthService
AuthService.validate_secret_key()
```

テスト: `TestJwtWeakKeyValidation` (6 テスト全 PASS)

---

### ルール 6: LLM 出力の JSON パース失敗 → HOLD (fail-closed)

| 評価 | PASS |
|------|------|
| 根拠 | `_parse_llm_response()` はあらゆるパース失敗を捕捉して `HOLD` を返す |

**実装 (`ai/service.py:336-368`):**
```python
except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
    return LLMDecision(provider=provider, action=TradeAction.HOLD, confidence=0, ...)
```

**クロスバリデーション (`ai/service.py:390-414`):**
- 2 つの LLM の判定が不一致 → `final_action=HOLD`
- API キー未設定 → `HOLD`

テスト: `TestLlmFailClosed` (7 テスト全 PASS)

---

### ルール 7: 金融計算は Decimal のみ（float 禁止）

| 評価 | PASS |
|------|------|
| 根拠 | 主要な金融フィールドすべてが `Decimal` 型で定義されている |

**確認済みフィールド:**
- `AaveSettings.min_health_factor: Decimal` — デフォルト `Decimal("1.6")`
- `AaveSettings.max_single_trade_usd: Decimal`
- `AaveSettings.warn_health_factor: Decimal`
- `ExchangeSettings.max_order_usd: Decimal`
- `AaveSystemState.health_factor: Optional[Decimal]`
- `AaveService._normalize_amount()` 戻り値: `Decimal`

**INFO:** `ExchangeSettings.usd_to_jpy_rate` は `float` だが、これは JPY 換算レート（参考値）であり、実際のオーダー金額計算には使われていない。

テスト: `TestDecimalOnlyFinancials` (6 テスト全 PASS)

---

### ルール 8: HARD_STOP モードで全 Aave 操作をブロック

| 評価 | PASS |
|------|------|
| 根拠 | `AaveService.execute_rebalance()` が `state.json` を読み込み、モードに応じて操作をブロックする |

**ブロック階層 (`service.py:177-249`):**

1. `state.json` が stale → NOOP
2. `state.emergency_stop=True` → NOOP (`"emergency_stop is True"`)
3. `state.circuit_closed=False` → NOOP (`"circuit_closed is False"`)
4. `mode=HARD_STOP` → NOOP (`"Mode=hard_stop: all Aave operations are blocked"`)
5. `mode=SAFE_MODE` + `action=BUY` → NOOP (`"Mode=safe_mode: BUY is blocked"`)
6. `monitoring.is_trading_allowed()=False` → NOOP

テスト: `TestHardStopBlocking` (6 テスト全 PASS)

---

### 追加確認: state.json アトミック書き込み

| 評価 | PASS |
|------|------|
| 根拠 | `state_manager.py` の `write_system_state()` がアトミック書き込みと `chmod 600` を実装している |

---

## 3. 総合評価

| ルール | 評価 | 備考 |
|--------|------|------|
| 1. ハードコード禁止 | **PASS** | 全 config が `get_env()` 使用 |
| 2. ログマスク | **PASS** | `[:6]...[-4:]` パターン実装済み |
| 3. HF < 1.6 → HARD_STOP | **PASS** | デュアルレイヤー実装 |
| 4. 緊急停止 OR ロジック | **PASS** | `existing OR triggered` |
| 5. JWT 弱キー拒否 | **WARN** | `validate_secret_key()` の startup 呼び出し未実装 |
| 6. LLM fail-closed | **PASS** | パース失敗→HOLD |
| 7. Decimal 型のみ | **PASS** | 主要金融フィールドは Decimal |
| 8. HARD_STOP ブロック | **PASS** | 6 段階ブロック実装済み |
| 9. state.json アトミック書込 | **PASS** | chmod 600 実装済み |
| 10. APP_ENV=prod → sandbox=False | **INFO** | 意図的設計、運用注意 |

---

## 4. 優先対処事項

### WARN-1: `validate_secret_key()` を startup イベントで呼び出す

**ファイル:** `backend/app/main.py`
**リスク:** 弱い JWT キーで本番環境が起動できてしまい、ルール 5 の保護が機能しない。
**推奨対処:** `startup_database` イベントハンドラ内に以下を追加:

```python
from app.auth.service import AuthService
AuthService.validate_secret_key()
```

---

## 5. テストスイート概要

| クラス | テスト数 | カバー対象 |
|--------|----------|-----------|
| `TestHardcodedSecrets` | 4 | ルール 1 |
| `TestLogMasking` | 3 | ルール 2 |
| `TestHealthFactorHardStop` | 5 | ルール 3 |
| `TestEmergencyStopOrLogic` | 4 | ルール 4 |
| `TestJwtWeakKeyValidation` | 6 | ルール 5 |
| `TestLlmFailClosed` | 7 | ルール 6 |
| `TestDecimalOnlyFinancials` | 6 | ルール 7 |
| `TestHardStopBlocking` | 6 | ルール 8 |
| **合計** | **41** | |

実行コマンド: `cd backend && python -m pytest tests/test_security_review.py -v`
結果: **41 passed, 0 failed**
