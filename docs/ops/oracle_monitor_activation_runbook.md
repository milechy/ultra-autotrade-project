# OracleMonitor 有効化 runbook（背景 oracle 監視 → 自動 emergency_stop）

> 対象: `app/automation/oracle_monitor.py`（接続監査 #3 で配線・Asana 1215080599381152）
> 前提 PR: feat/oracle-monitor-wiring（scheduler 結線・flag-gated・dormant）
> 分類: **安全装置の本番有効化** = 本番 VPS は 3 段プロトコル（@phase1-investigator → @phase2-implementer → @phase3-deployer）経由。直接 ssh / `.env.production` 直接編集は禁止。

---

## これは何か

Chainlink oracle の staleness / 価格乖離を**定期ポーリング**で監視し、異常時に
`MonitoringService.activate_emergency_stop` を**自動発火**する背景ループ。
deposit/supply 実行時にインライン検査する既存 `aave/oracle_checker.py`（per-tx HARD_STOP）
とは別レイヤ＝継続監視で proactive に停止する補完装置。

発火条件（OracleMonitor 既定）:
- oracle 異常（staleness 超過 or 乖離超過）**かつ** 直近 HF < 1.8、または
- 極端異常（age > 24h or 乖離 > 30%）は HF 不問で fail-safe 発火。

---

## dormant の保証（現状＝本番無影響）

以下のどちらかが欠ければ**一切稼働せず emergency_stop も発火しない**:
1. `ENABLE_ORACLE_MONITOR` が truthy（既定 `false`）
2. 監視 feed が解決できる（下記いずれか）

---

## feed 設定（単一ソース推奨）

feed アドレスを**二重管理しない**。解決順は:

1. `ORACLE_MONITOR_FEEDS`（明示上書き・monitor 専用）
   `[{"name":"USDC","feed_address":"0x...","rpc_url":"https://..."}, ...]`
2. **`AAVE_ORACLE_ASSETS_JSON`（既存 oracle_checker と共有・推奨）**
   `[{"asset":"USDC","chainlink_feed":"0x...","rpc_url":"https://...", ...}, ...]`
   から `chainlink_feed` + `rpc_url` が揃うエントリを自動採用。

→ **通常運用では `AAVE_ORACLE_ASSETS_JSON` をそのまま再利用**し、有効化は
`ENABLE_ORACLE_MONITOR=1` を足すだけ。新たな feed リストを書かない（drift 防止）。

### 参考: コードに存在する検証済み feed（cross-check 用）
- ETH/USD (Base mainnet): `0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70`
  （`app/partner/wallet_balance_service.py` で本番使用中）
- USDC/USD 等は本番 `AAVE_ORACLE_ASSETS_JSON` の値を正とする（サーバ上で確認）。

---

## 段階ロールアウト

### Phase 1: staging-v4 で観測（観測のみ・資金影響なし）
1. staging-v4 の env に `ENABLE_ORACLE_MONITOR=1` を追加（`AAVE_ORACLE_ASSETS_JSON` は既存値を流用）。
2. backend 再起動（`docker compose up -d --no-deps --build backend`）。
3. ログ確認（5 分間隔）:
   ```
   Starting oracle monitor loop (interval: 300s, feeds: N)
   oracle_monitor_loop: anomaly=false, emergency=false, fetch_failures=0
   ```
   - `feeds: 0` なら feed 未解決 → `AAVE_ORACLE_ASSETS_JSON` を確認。
   - 平常時に `emergency=true` が出る → 閾値/feed 誤り。**有効化を中止**して調査。
4. 最低 24-48h、平常時に false / fetch_failures=0 が続くことを確認。

### Phase 2: production（3 段プロトコル）
1. @phase1-investigator: 本番 `AAVE_ORACLE_ASSETS_JSON` の feed/rpc を read-only 確認。
2. @phase2-implementer: `ENABLE_ORACLE_MONITOR=1` 追加プラン + ロールバック（flag を消すだけ）提示・承認待ち。
3. @phase3-deployer: 承認後に env 追加 → backend 再起動 → ログで `feeds: N` / `anomaly=false` 確認。
4. ロールバック: `ENABLE_ORACLE_MONITOR` を消して再起動（即 dormant 化）。

---

## 検証チェックリスト（完了宣言前）
- [ ] 起動ログに `Starting oracle monitor loop (... feeds: N>0)`
- [ ] 平常時に `emergency=false` が継続（誤発火なし）
- [ ] `fetch_failures` が常時 0（RPC/feed 到達性 OK）
- [ ] 意図的 stale テスト（任意・staging）で emergency 発火と Slack 通知を 1 度確認
- [ ] ロールバック（flag 削除 → dormant）を確認

---

## 注意
- 平常時の誤発火は**全 Aave 操作停止**につながるため、staging 観測を必ず先行する。
- 閾値（staleness 1h / 乖離 10% / extreme 24h・30% / HF guard 1.8）は OracleMonitor 既定。
  変更が要る場合は `OracleMonitor.__init__` 引数で調整（本 runbook 外）。
