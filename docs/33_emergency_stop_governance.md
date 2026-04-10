# 緊急停止ガバナンス

**バージョン:** 1.0  
**最終更新日:** 2026-04-01  
**担当:** Ultra AutoTrade 運用チーム

---

## 1. 概要

Ultra AutoTrade の緊急停止機能は、資産を守るための最終防波堤です。
一度発動すると、明示的な解除操作が行われるまで全ての自動取引が停止します。
この文書は、緊急停止の発動権限・条件・手順・解除条件を定義します。

---

## 2. 発動権限

| 発動者 | 手段 | 詳細 |
|--------|------|------|
| **管理者ユーザー（ADMIN ロール）** | `POST /api/automation/emergency-stop` | 認証済み管理者がいつでも手動発動・解除可能 |
| **パートナーユーザー（PARTNER ロール）** | `POST /api/automation/emergency-stop` | 手動発動のみ可能。**解除（resume）は ADMIN ロールのみ**。 |
| **自動監視システム** | `MonitoringService.record_health_factor()` | HF < 1.6 を検知した場合に自動発動 |
| **サーバー再起動** | state.json 復元 | 起動時に `emergency_stop=True` が保存されていれば自動復元 |

---

## 3. 発動条件

### 3-1. ヘルスファクター (HF) 異常

```
HF < 1.6 → HARD_STOP（緊急停止）
```

- `MonitoringService.record_health_factor()` が呼ばれるたびに自動チェック
- Aave V3 からリアルタイム取得される HF が閾値を下回った瞬間に発動
- 発動理由は `state.json` の `reason` フィールドに記録

### 3-2. Oracle 異常（推奨実装）

以下の条件で HOLD（取引停止）を推奨する。緊急停止への昇格は運用判断による：

- Chainlink price feed の更新が 1 時間以上停止（`is_stale=True`）
- 前回価格からの乖離が 10% 超（`is_circuit_breaker=True`）
- L2 Sequencer がダウン中または回復後のグレース期間中

詳細: `backend/app/aave/oracle_checker.py`

### 3-3. Reserve Pause/Freeze

以下の条件で HOLD（取引停止）を推奨する。緊急停止への昇格は運用判断による：

- Aave V3 の reserve が `isPaused=True`
- Aave V3 の reserve が `isFrozen=True`
- reserve が `isActive=False`

詳細: `backend/app/aave/reserve_monitor.py`

### 3-4. 手動発動

- 管理者が判断した任意のタイミングで発動可能
- 発動理由を API リクエストボディに含めること（監査証跡として記録される）

---

## 4. 停止範囲

緊急停止が発動されると、以下の処理が全て停止する：

| 対象 | 停止内容 |
|------|----------|
| 自動取引ワークフロー | `POST /automation/process-news` が 503 を返す（`is_trading_allowed()=False`） |
| Aave 操作 | `deposit()` / `withdraw()` / `rebalance()` 全て停止 |
| AI 判定 | 判定は実行されても execute フェーズで停止 |
| Exchange 注文 | Bybit への注文送信が停止 |

**停止しないもの:**

- 監視・ログ収集
- ダッシュボード参照 (`GET /automation/status`)
- HF の継続監視（停止後も monitoring は継続）

---

## 5. OR ロジック実装との整合性

緊急停止は **OR 条件** で管理される。一度 `True` になった `emergency_stop` フラグは、
`clear_emergency_stop()` が明示的に呼ばれるまで `False` に戻らない。

```python
# state_manager.py の更新ロジック（概念）
final_emergency_stop = existing_emergency OR hf_triggered_emergency
```

**重要:** 複数の条件が緊急停止を発動した場合でも、全ての条件が解消されてから
手動で解除操作を行うこと。

---

## 6. 監査証跡

### 6-1. state.json

```json
{
  "emergency_stop": true,
  "mode": "HARD_STOP",
  "health_factor": "1.45",
  "last_update": "2026-04-01T10:00:00+00:00",
  "reason": "health factor 1.45 below emergency threshold 1.6",
  "circuit_closed": false
}
```

ファイルパス: `backend/state.json`（デプロイ環境によって変わる）

### 6-2. アプリケーションログ

緊急停止発動時に以下のレベルでログが記録される：

```
EMERGENCY: Emergency stop activated: <reason>
```

ログは Docker ログに出力される。確認コマンド：

```bash
docker logs <backend-container> 2>&1 | grep -i "emergency"
```

### 6-3. Slack 通知

`CompositeNotificationService` が設定されている場合、以下のメッセージが送信される：

- **発動時:** `🚨 緊急停止が発動されました` (severity: EMERGENCY)
- **解除時:** `✅ 緊急停止が解除されました` (severity: INFO)

---

## 7. 解除条件

緊急停止は以下の **全条件** を満たしてから解除すること：

| 条件 | 確認方法 |
|------|----------|
| HF が安全域に回復（> 1.8 推奨） | `GET /aave/status` で health_factor を確認 |
| Oracle 異常が解消 | Chainlink feed の更新が再開されたことを確認 |
| Reserve 異常が解消 | Aave ダッシュボードで reserve 状態を確認 |
| 手動停止の原因が解消 | 発動した管理者が原因解消を確認 |

---

## 8. 解除手順

### Step 1: 原因確認

```bash
# state.json を確認
cat backend/state.json

# 最新ログを確認
docker logs <backend-container> 2>&1 | grep -i "emergency\|error" | tail -50
```

### Step 2: HF の確認（Aave 関連の場合）

```bash
curl -H "Authorization: Bearer <admin-token>" \
  https://api.ultra-autotrade.example.com/aave/status
```

`health_factor` が `1.8` 以上であることを確認する。

### Step 3: 解除 API の呼び出し

```bash
curl -X POST \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  https://api.ultra-autotrade.example.com/automation/emergency-stop/resume
```

### Step 4: 解除確認

```bash
curl -H "Authorization: Bearer <admin-token>" \
  https://api.ultra-autotrade.example.com/automation/status
```

レスポンスの `is_trading_paused` が `false` であることを確認する。

### Step 5: 監視継続

解除後 30 分間は以下を継続監視する：

- HF の変動
- AI 判定の正常動作
- Bybit 注文の送信状況（`dry_run=false` 環境のみ）

---

## 9. エスカレーション

| 状況 | 対応 |
|------|------|
| 解除 API が 500 を返す | バックエンドログを確認し、state.json を手動修正 |
| state.json が破損 | バックアップから復元、または `get_safe_default_state()` が適用される |
| HF が回復しない | Aave ポジションの手動清算を検討（プロトコル直接操作） |
| Slack 通知が届かない | `SLACK_WEBHOOK_URL` 環境変数を確認 |

---

## 10. 関連ファイル

- `backend/app/automation/monitoring_service.py` — 緊急停止ロジック本体
- `backend/app/automation/automation_router.py` — `/automation/emergency-stop` エンドポイント
- `backend/app/aave/state_manager.py` — state.json の読み書き
- `backend/app/aave/oracle_checker.py` — Oracle 鮮度チェック
- `backend/app/aave/reserve_monitor.py` — Reserve 状態監視
- `docs/13_security_design.md` — セキュリティ設計全般
- `docs/08_automation_rules.md` — 自動化ルール定義
- `docs/15_rollback_procedures.md` — ロールバック手順
