# Postmortem Follow-up Status

最終更新: 2026-05-20

---

## 凡例
- ✅ 完了 (PR merge 済み)
- 🔴 未対応 (優先度高)
- 🟡 一部対応
- ⏳ 確認中

---

## 2026-05-17: Loki postgres カスケード

**RCA ファイル:** `2026-05-17_loki_postgres_cascade.md`

| 優先度 | アクション | 状態 | 備考 |
|---|---|---|---|
| P0-1 | `docker-compose.production.yml` loki に `healthcheck:` 追加 | 🔴 未対応 | `wget -q --spider http://localhost:3100/ready` を追加必要 |
| P0-2 | Loki `/ready` Gate 8 (外形 healthcheck 拡張) | 🔴 未対応 | deploy スクリプトに組込必要 |
| P1-3 | 朝プロトコル業務サニティに Loki 死活確認組込 | 🔴 未対応 | CLAUDE.md §9 に追記必要 |
| P1-4 | logging driver `json-file` 化 | 🟡 一部対応 | loki/promtail 自体は json-file 済。**postgres/backend-blue/backend-green/nginx/frontend の 5 サービスが loki driver のまま** (実機確認済) |

**P1-4 の実機状態 (2026-05-20 確認):**
```
loki driver 残存:  postgres, backend-blue, backend-green, nginx, frontend (5件)
json-file 適用済: loki, promtail, cloudflared (3件)
```

→ **P1-4 は Tier S 直列枠で 1 PR 必要。** loki が落ちると 5 サービスが道連れになるリスクが継続中。

---

## 2026-05-18: L1-L6 healthcheck デプロイ記録

**RCA ファイル:** `2026-05-18_healthcheck_deploy.md`

| 優先度 | アクション | 状態 | 備考 |
|---|---|---|---|
| P1 | L2 閾値を 270 分に修正 | ✅ 完了 | PR #274 (dcdf330) merged |
| P1 | ログパス不整合 (morning-report 連携) | ⏳ 確認中 | 別 Tier B タスク化予定 |

---

## 2026-05-18: transactions_zero RCA (HOLD 偏向)

**RCA ファイル:** `2026-05-18_transactions_zero_rca.md`

| 優先度 | アクション | 状態 | 備考 |
|---|---|---|---|
| 段階1 | Tier B 修正 2 件 (Perplexity / rebalance module) | ✅ 完了 | PR 作成済・merge 確認必要 |
| 段階2 | 山本さんへの状況報告 DM | ⏳ hkobayashi 対応 | 事前 DM 必須。効果観測まで |
| 段階3 | HOLD 偏向の根本対策 (AI prompt 調整) | 🔴 未着手 | 段階2 の効果観測後に実施 |

---

## 2026-05-19: production stack コンテナ消失

**RCA ファイル:** `2026-05-19_production_stack_container_loss.md`

| 優先度 | アクション | 状態 | 備考 |
|---|---|---|---|
| P0 | RCA 確定 (仮説 5 つ残存) | 🔴 未確定 | docker events ログ取得・journalctl 確認未完了 |
| P1 | staging 自動復旧 (down → up cron or watchdog) | 🔴 未対応 | - |

---

## 優先度まとめ (2026-05-20 時点)

| 順位 | アクション | 分類 | 所要時間 |
|---|---|---|---|
| 1 | P1-4: logging driver json-file 化 (5 サービス) | Tier S 1 PR | 30-60 分 |
| 2 | P0-1: loki healthcheck 追加 | Tier S (上記と合わせて 1 PR 可) | 10 分 |
| 3 | production stack RCA 確定 (docker events 取得) | read-only Phase 1 | 30 分 |
| 4 | 朝プロトコルへの Loki 死活確認組込 | CLAUDE.md 更新 Tier S | 15 分 |
| 5 | 山本さん DM (段階2) | hkobayashi 専権 | - |
