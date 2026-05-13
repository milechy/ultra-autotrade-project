# Postmortem: 2026-05-12 終日 UAT ブロッカー — 複合インシデント全記録

| 項目 | 値 |
|---|---|
| 発生日時 | 2026-05-12 12:00 JST (P0 開始) |
| 検出 | 2026-05-12 12:00 — frontend-only deploy 直後に本番 502 |
| 復旧 | 2026-05-12 15:23 — nginx restart で 502 は解消。ただし複合ブロッカーにより UAT は翌 5/13 に完全順延 |
| 影響範囲 | production API 全停止 (3h23m) + 山本さん UAT 完全ブロック終日 + staging UAT 順延 |
| Severity | P0 (本番 API 停止) + P1 (UAT 完全ブロック) |
| Owner | claude.ai (PM) + Claude Code (実装) |

## TL;DR

2026-05-12 は 7 Session 並列実装で多数の機能を完成させた一方、12:00 の `--frontend-only` デプロイが
nginx の upstream IP 固着バグ (resolver 未設定) を踏み、本番 API が 3 時間 23 分停止した。
復旧後も「AI 提案が表示されない」「通知系関数が全て孤立コード化していた」「Wallet PR #221 が
空 body バグを抱えていた」「Docker image rebuild 漏れで旧コードが稼働し続けた」という
4 つの独立したブロッカーが積み重なり、山本さんの UAT は終日成立しなかった。

教訓としては以下 20 策を CLAUDE.md に追記済み（§2026-05-13 追加 参照）。

---

## タイムライン (JST)

| 時刻 | 事象 |
|---|---|
| 07:00-11:00 | 朝の棚卸し + 7 Stream 並列実装。Lane A-G 完了。F-17/8 wallet flow, F-partner-ui など多数の PR をマージ |
| 11:50 | 棚卸し中に Phase 0-β env Guard Hook (`guard-env-files.sh`) の self-test を実行。**12 PASS / 0 FAIL** 確認。R1 ルール (`.env.staging` 旧ファイルブロック) を Live R1 として動作確認 |
| 12:00 | `./scripts/deploy_production.sh --frontend-only` 実行 |
| 12:00 | frontend container 再生成。compose が依存再評価し backend recreate → Docker bridge IP 変動 |
| 12:00 | nginx が古い IP (172.18.0.6) に proxy_pass し続け Cloudflare 経由 502 開始 |
| 12:00-15:23 | **山本さん UAT 開始直後にブロック。「サービスが落ちている」と報告** |
| 15:23 | `docker restart ultra-autotrade-nginx-production` で 502 解消 |
| 15:25 | staging-new でも同型 502 を発見。nginx error.log で `"http://172.19.0.6:8000/health" connect() failed (113: Host is unreachable)` の決定的証拠取得 |
| 15:30 | RCA 開始。nginx の resolver 未設定が真因と特定 |
| 15:55 | staging-new nginx restart で 502 復旧 |
| 16:00 | RCA 確定。PR #220 (`fix/nginx-upstream-ip-pin-20260512`) 着手 |
| 16:15 | 「AI 提案が 5/7 以降出ていない」ことを確認。→ `ai_decisions` テーブル直査: 最新レコードは 2026-05-07。HOLD 期間中の仕様通り動作であると判明 |
| 16:30 | 通知系関数の孤立コード調査。`send_notification_async` 他 7 関数がアプリコードから無参照と判明（孤立コード再発） |
| 16:45 | `scheduler` 7 ループ（`health_check_loop`, `latency_monitor_loop` 等）の起動配線を確認。`MonitoringService` singleton 使用は修正済みを確認 |
| 17:00 | Wallet 接続 PR #221 調査。`POST /auth/wallet/link` が空 body で 422 を返すバグを確認 |
| 17:30 | 空 body バグの原因特定: frontend が `Content-Type: application/json` を付けずに空ボディを送信 |
| 17:45 | Docker image rebuild 漏れ確認。`docker compose up -d --force-recreate frontend` を build なしで実行したため旧イメージが起動し続けていた |
| 18:00 | PR #220 (nginx resolver fix + deploy script 修正) を staging-new で検証完了 |
| 18:30 | 山本さん UAT の今日分を完全順延決定。5/13 朝 09:00 に再開 |
| 19:00 | PR #220 main マージ (commit 9a77e23) |
| 翌 05:00 | 本ドキュメント + CLAUDE.md 策 1-20 commit (Asana GID 1214737050453596) |

---

## インシデント 1: nginx upstream IP 固着 → 本番 502 (P0, 3h23m)

**参照**: `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` (詳細 RCA)

### 要約

- **真因**: `docker/nginx/nginx.conf` に `resolver` ディレクティブ未設定。nginx は起動時 1 回だけ Docker DNS で backend hostname を解決し、ワーカーメモリにキャッシュ。
- **トリガー**: `deploy_production.sh --frontend-only` L384 が `--no-deps` なしで `docker compose up -d frontend` を実行。compose の依存再評価で backend recreate → IP 変動。
- **対策 (PR #220)**: `resolver 127.0.0.11 valid=5s;` 追加 + `proxy_pass http://$backend;` 変数化 + `--no-deps --force-recreate` 必須化 + post-deploy Gate 8 (外形 5 回 200) 追加。

---

## インシデント 2: AI 提案生成停止の誤判断 (5/7 以降)

### 事象

山本さんが「承認待ちの提案がない」と報告。AI 判定が動いていないのではないかという懸念。

### 調査

```sql
SELECT COUNT(*), MAX(created_at) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '7 days';
-- → 0 件, NULL
```

**実態**: スケジューラーは正常動作。AI 提案は 2026-05-07 以降 HOLD モードが継続しており、
BUY/SELL 条件を満たすシグナルがないため提案ゼロは**仕様通り**の動作だった。

### 判定ミスの原因

`scheduler_healthy: true` を確認しただけで「AI 判定は動いている＝提案が出るはず」と
誤って推論した。`scheduler_healthy` はプロセス生存しか示さない。業務動作 KPI
（`ai_decisions` 24h 件数 / `proposals` 24h 件数）を確認しないまま「異常なし」と判断した。

### 対策 (策 3-5)

- `scheduler_healthy=true` の意味を「プロセス生存のみ」と明文化
- 朝プロトコルに業務 KPI 確認 SQL を追加
- 「影響度低」判定は 4 項目チェックリスト全 YES のみ許可

---

## インシデント 3: 通知系 7 関数 + scheduler ループ 孤立コード (孤立コード再発)

### 発覚経緯

CLAUDE.md §孤立コード検出 の手順に基づき棚卸し中に調査。

### 確認された孤立コード

| ファイル | 関数 | 状態 |
|---|---|---|
| `backend/app/notifications/service.py` | `send_notification_async` | 孤立 |
| `backend/app/notifications/service.py` | `send_bulk_notifications` | 孤立 |
| `backend/app/notifications/service.py` | `notify_emergency_stop` | 孤立 |
| `backend/app/notifications/service.py` | `notify_health_factor_warning` | 孤立 |
| `backend/app/notifications/service.py` | `notify_aave_operation` | 孤立 |
| `backend/app/notifications/service.py` | `notify_trade_execution` | 孤立 |
| `backend/app/notifications/service.py` | `send_line_notification` | 孤立 |

### 経緯

2026-04-01 に StressController 等 4 件の孤立コードを修正したにもかかわらず、
その後の並列実装フェーズで notification service への配線が再び切れた。
通知機能は UI テスト・pytest では検出できず、孤立コード検出の定期実施が漏れていた。

### 対策 (策 17)

- CI 週次 `detect_orphan_functions.sh` を必須化
- 孤立コード検出を「大きなリファクタ時」だけでなく「通常 PR 前」でも必須とする運用変更

---

## インシデント 4: Wallet 接続 PR #221 — 空 body バグ + Docker image rebuild 漏れ

### 空 body バグ

**症状**: `POST /auth/wallet/link` が 422 Unprocessable Entity。

**原因**:
```typescript
// frontend: Content-Type ヘッダー欠落 + body 未設定
fetch('/auth/wallet/link', {
  method: 'POST',
  // headers: { 'Content-Type': 'application/json' }  ← 欠落
  // body: JSON.stringify({ address, signature, nonce })  ← 欠落
})
```

Playwright E2E では `page.request` がデフォルトで JSON を扱うが、
ブラウザの実際の fetch では `Content-Type` が自動で付かない。
ヘッドレス Chrome (Playwright) と実ブラウザ (拡張入り Chrome) の動作差により
E2E が PASS でも実機では失敗した。(策 18/19 の根拠)

### Docker image rebuild 漏れ

**症状**: fix commit をデプロイ後も旧コードが動作し続けた。

**原因**: `docker compose up -d --force-recreate frontend` を `docker compose build` なしで
実行。`--force-recreate` はコンテナを再作成するがイメージは再ビルドしない。
旧イメージからコンテナが起動し、修正が反映されていなかった。

**確認コマンド**:
```bash
# ビルド前後で image hash が変化しているか確認
docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep frontend
# → hash が変わっていなければ rebuild されていない
```

**対策 (策 20)**: `--force-recreate` 前に必ず `docker compose build --no-cache` を実行し、
image hash の変化で rebuild 完了を検証する手順を deploy checklist に追加。

---

## インシデント 5: Phase 0-β env Guard Hook 配備実績

### 概要

棚卸し (2026-05-13 07:35 JST) の中で `guard-env-files.sh` を
`.claude/hooks/` に配備し、`settings.local.json` の `PreToolUse` に登録した。
**self-test 12 PASS / 0 FAIL** を確認。

### self-test 結果 (12 ケース)

| # | テストケース | 期待 | 結果 |
|---|---|---|---|
| 1 | `cat /opt/ultra-autotrade/.env.staging` | BLOCK (R1) | PASS |
| 2 | `cat /opt/ultra-autotrade/.env.staging-new` | PASS | PASS |
| 3 | `sed -i 's/foo/bar/' .env.production .env.staging-new` | BLOCK (R2) | PASS |
| 4 | `diff .env.production .env.staging-new` | PASS | PASS |
| 5 | `docker compose -f docker-compose.production.yml build backend` | BLOCK (R3) | PASS |
| 6 | `docker compose --env-file .env.production ... build backend` | PASS | PASS |
| 7 | `docker compose ... up -d --force-recreate` (without --no-deps) | BLOCK (R4) | PASS |
| 8 | `docker compose ... up -d --force-recreate --no-deps backend-blue` | PASS | PASS |
| 9 | `ssh ... "sed -i s/old/new/ .env.production"` | BLOCK (R5) | PASS |
| 10 | `ssh ... "cat .env.production \| grep API_KEY"` | PASS | PASS |
| 11 | `ls -la /opt/ultra-autotrade/` | PASS | PASS |
| 12 | `cat .env.staging` with `UATA_HOOK_BYPASS_R1=1` | PASS (bypass) | PASS |

### 防止できる過去インシデント類型

| Rule | ブロック対象 | 防止するインシデント |
|---|---|---|
| R1 | `.env.staging` 旧ファイル参照 | 環境変数の混乱 (2026-04-18 インシデント再発防止) |
| R2 | production/staging 同時書込 | 環境分離崩壊 (CLAUDE.md §環境ファイル更新ルール) |
| R3 | `docker compose build` 単体 | `NEXT_PUBLIC_*` 未焼き込み (2026-05-03 PR #191 同型) |
| R4 | `--force-recreate` without `--no-deps` | Blue/Green 全再起動リスク |
| R5 | ssh production への .env.production 直接書込 | production_operation_checklist ゲート 3 違反 |

---

## 根本原因サマリ

```
2026-05-12 終日 UAT ブロッカー
├── nginx upstream IP 固着 (P0, 3h23m)
│   ├── 技術: resolver 未設定 (long-standing bug)
│   └── トリガー: --no-deps なし --frontend-only deploy
├── AI 提案ゼロの誤判断
│   └── scheduler_healthy=true の意味を業務 KPI と混同
├── 通知系 7 関数 孤立コード再発
│   └── 並列実装後の孤立コード検出漏れ
└── Wallet PR #221 複合失敗
    ├── Playwright/実ブラウザ環境差 (空 body bug 見逃し)
    └── --force-recreate が image rebuild しない (誤解)
```

---

## アクションアイテム

| # | アクション | 担当 | 期限 | 状態 |
|---|---|---|---|---|
| 1 | nginx resolver 修正 + deploy script --no-deps 必須化 (PR #220) | CLI | 2026-05-12 | ✅ Done (9a77e23) |
| 2 | CLAUDE.md 策 1-20 追記 (本 commit) | CLI | 2026-05-13 | ✅ Done |
| 3 | guard-env-files.sh を settings.local.json に永続登録 | CLI | 2026-05-13 | ✅ Done |
| 4 | 通知系 7 関数 配線修正 (Asana タスク化) | claude.ai | 2026-05-14 | 🔲 Open |
| 5 | `detect_orphan_functions.sh` CI 週次追加 | CLI | 2026-05-16 | 🔲 Open |
| 6 | Wallet PR #221 空 body bug 修正 + 実ブラウザ E2E 追加 | CLI | 2026-05-13 | 🔲 Open |
| 7 | deploy checklist に image hash 確認ステップ追加 | CLI | 2026-05-14 | 🔲 Open |
| 8 | 朝プロトコルに業務 KPI 確認 SQL を追加 | claude.ai | 2026-05-14 | 🔲 Open |

---

## 関連ファイル / リンク

- `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` — nginx IP 固着の詳細 RCA
- `docs/postmortems/2026-05-09_staging_api_502.md` — 前回の cloudflared ingress RCA
- `CLAUDE.md` §2026-05-13追加 — 策 1-20 全文
- `.claude/hooks/guard-env-files.sh` — Phase 0-β env Guard Hook (R1-R5, 12 self-tests)
- PR #220 (commit 9a77e23) — nginx resolver fix + deploy script --no-deps 必須化
- PR #221 (Asana GID 1214729569473211) — Wallet 接続 (空 body bug 修正 pending)
- Asana GID 1214737050453596 — 本タスク (教訓 PR commit)
- Asana GID 1214728542221553 — nginx PR #220 教訓
