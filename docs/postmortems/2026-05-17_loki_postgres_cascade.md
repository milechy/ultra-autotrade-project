# Postmortem: 2026-05-15 Loki 半死状態 → Postgres logging driver block 連鎖

- **発生日**: 2026-05-15 07:31 JST 〜 08:18 JST (Loki 半死状態 ~47 分)
- **検出日**: 2026-05-17 09:00 JST (今朝の事故調査で発覚 / 49 時間遅延検出)
- **本 Postmortem 作成**: 2026-05-17 (Lane B-4)
- **影響範囲**: production / staging-new 両方 (Loki logging driver 経由ログ収集が全 service で停止)
- **担当**: Lane B-4 (worktree-lane-b4-loki-rca)
- **関連 Lane**: S-1 (logging driver json-file 切替), S-2 (backup_db.sh 修正)

## 1. 起きたこと

### 1-1. Loki 半死状態の経緯

| 時刻 (JST) | 事象 |
|---|---|
| 2026-05-14 07:33 | Loki 通常起動 (warn のみ、healthy) |
| 2026-05-15 07:31:49 | Loki 再起動 (起動完了、warn のみ) |
| 2026-05-15 07:31:55 〜 08:17:55 | Promtail が Loki に push できず "connection refused" / "could not transfer logs unexpected EOF" を多発 |
| 2026-05-15 08:17:58 | Loki ログに `scheduler_processor.go:106 ... rpc error: code = Canceled desc = context canceled` が **10 件連続** で出現 (シャットダウン直前パターン) |
| 2026-05-15 08:18:19 | Loki container 再起動完了 (起動以降 error 0 件) |
| 2026-05-15 08:18:20 | Promtail も `enable watchConfig` で再接続成功 |
| 2026-05-15 08:18 〜 2026-05-17 (現在) | **46 時間連続 healthy** (/ready 200, ingestion 正常) |

### 1-2. 連鎖した影響

`docker-compose.production.yml` で **以下の全 service が `logging.driver: loki` を使用**:

- postgres (L110-116)
- backend-blue (L158-164)
- backend-green (L195-201)
- nginx (L222 以降)

Loki が半死中、Docker の loki logging driver は push retry を行う (loki-retries: 3, loki-timeout: 10s)。
**push が retry buffer を埋め切ると、Docker daemon は該当 container の stdout 書き込みを block する**
(Docker logging driver の既知挙動)。

→ 結果として postgres / backend-blue / backend-green が「ログ出力で hang する → request 処理が遅延する」
状態に陥り、これが今朝発覚した「業務 KPI 異常」の遠因となった可能性が高い。

### 1-3. 検出が 49 時間遅れた理由 (RC-2 = "Loki の死亡を誰も検知できなかった")

- `/health` endpoint には Loki / Promtail / logging pipeline の状態が含まれていない
- Slack alert で Loki down 通知する仕組みが存在しない
- promtail の error log は Loki に push できないので、Loki が死ぬと promtail の error 自体が見えなくなる (catch-22)
- 朝プロトコル (CLAUDE.md §朝プロトコル拡張) には Loki 状態確認が含まれていなかった

## 2. 真因 (RCA)

### 真因 A: grafana/loki:2.9.0 の `scheduler_processor context canceled` パターン

`scheduler_processor.go:106` で `rpc error: code = Canceled desc = context canceled` が
連続出力されてからの **silent freeze** は grafana/loki 2.9 系の既知不安定パターン。
正常時は warn 程度しか出ない component から error level が出ているため、internal scheduler の
hard fault が発生している。

### 真因 B: Loki dies = Docker daemon が container stdout block する設計

Loki logging driver は **fail-closed 設計**で、push に失敗すると container 側の log write を
block する (data loss を避ける設計判断)。これにより Loki 半死 → application container 半死、
という連鎖障害が起きる。

Lane S-1 で **logging driver を json-file に切替** することでこの連鎖を断つ
(promtail が後段で /var/lib/docker/containers/ から pull 型で吸い上げる pattern に変更)。

### 真因 C: 監視の欠落 (RC-2 本質)

Loki container の生死を監視する手段が存在しなかった。
- `/health` は application backend のみカバー
- `docker ps` レベルでは Loki は "running" のままだった (silent freeze)
- Slack alert なし
- promtail error log は Loki 死亡時に消える (catch-22)

## 3. 現在の状態 (2026-05-17 検証結果)

Lane B-4 SSH 経由 `ultra@77.42.46.155` で確認:

```
==== Loki container 詳細 ====
Status: running
Started: 2026-05-15T08:18:19.784766432Z  (連続稼働 ~46h)
Restart: 0
Image: grafana/loki:2.9.0

==== Loki port listen ====
:::3100 LISTEN (1/loki)
:::9096 LISTEN (1/loki)

==== HTTP /ready ====
ready  (HTTP 200)

==== メモリ/CPU ====
74.86 MiB / 7.564 GiB (0.97%), CPU 0.42%

==== /loki disk ====
8.5 MB (WAL/chunks 詰まりなし)

==== ingestion ====
loki_request_duration_seconds_count{route="loki_api_v1_push", status_code="204"} = 44,665
(204 は正常な push 受信)
loki_distributor_bytes_received_total = 16.9 MB

==== 直近 30 分の ingest ====
backend-blue:  187 lines
backend-green: 190 lines
nginx:           1 line

==== error level ====
直近 30 分: 0 件
起動 (5/15 08:18) 以降全期間: 10 件 (= 5/15 08:17 停止直前の context canceled の残骸)

==== Promtail ====
Status: running
Started: 2026-05-15T08:18:19.774503813Z
Restart: 0
直近の error log: docker container disappear 系のみ (運用上 noise、害なし)
push 経路: 正常 (上記 204 が証拠)
```

**結論**: Loki は 5/15 08:18:19 の再起動で完全復旧済み、46 時間連続 healthy。
Lane B-4 prompt の「HTTP /ready: 503 / 半死状態」は **2026-05-15 朝の事実** で、
現時点 (2026-05-17) では既に解消している。

## 4. DoD 達成状況

| DoD 項目 | 状態 | 証拠 |
|---|---|---|
| Loki HTTP /ready 200 応答 | ✅ 達成 | `docker exec ... wget -qO- http://localhost:3100/ready` → `ready` |
| Loki ログに 30分間 error level なし | ✅ 達成 | `docker logs --since 30m ... \| grep level=error \| wc -l` = 0 |
| Promtail からの Loki 接続成功 | ✅ 達成 | `loki_request_duration_seconds_count{status_code="204"}` = 44,665、直近 30 分 backend-blue 187 lines / backend-green 190 lines / nginx 1 line ingest 確認 |
| 真因 RCA 文書化 | ✅ 達成 | 本文書 (`docs/postmortems/2026-05-17_loki_postgres_cascade.md`) |
| PR 作成 + description に "DoD: Loki完全復旧 + 真因RCA文書化" | ✅ Phase 3 末で実施 | - |

## 5. 再発防止 (Lane B-4 では実装しない / 別 Lane / 別 PR で対応)

| 対策 | 担当 | 期限 |
|---|---|---|
| logging.driver を loki → json-file に切替 (連鎖断絶) | **Lane S-1** | 今日中 |
| promtail を pull 型 (`/var/lib/docker/containers/*/*-json.log`) のみに変更 | Lane S-1 | 今日中 |
| `/health` に Loki /ready check 追加 | Lane B-3 (healthcheck l1-l6) 検討 | 別 Lane |
| 朝プロトコルに Loki /ready + ingestion 直近 30 分 件数の SQL/curl を追加 | CLAUDE.md §朝プロトコル拡張 改訂 | 別 PR |
| grafana/loki を 2.9 系最新 patch (2.9.13 等) に upgrade | Tier S compose 変更、別 Asana | 別 PR |

## 6. Lane B-4 で実施した作業

- ✅ STEP 1: Loki container 状態調査 (status / port / mem / disk / log)
- ✅ STEP 2: Promtail 状態 + E2E ingestion 確認 (LogQL query)
- ✅ STEP 3: grafana/loki:2.9.0 既知 issue 評価 (`scheduler_processor context canceled` パターン特定)
- ✅ Phase 2: 4 案提示 → 「案 A: 文書化のみ」承認取得 (再起動不要、既に復旧済み)
- ✅ Phase 3: 本 postmortem 文書化
- ⏭️ 範囲外: 本番 logging driver の変更 (Lane S-1)、backup_db.sh の修正 (Lane S-2)、山本さん DM 送信、別 Lane の作業

## 7. 教訓 (CLAUDE.md §教訓-2026-05-17 候補)

### 教訓 1: Lane prompt の「事実」と現状の乖離は CLI 経由で必ず再確認する (鉄則8 強化)

Lane B-4 prompt には「Loki HTTP /ready: 503」「ログ最終: 2026-05-15 08:18:20」と書かれていたが、
SSH 確認の結果、両方とも 2026-05-15 朝時点の事実で、2026-05-17 現在は復旧していた。
Lane prompt の「事実」セクションは作成時刻のスナップショットであり、Lane 着手時に必ず再確認する。

### 教訓 2: docker logging driver fail-closed 設計の連鎖障害

`logging.driver: loki` は Loki 死亡時に application container の stdout を block する。
これは「ログ欠損より hang を取る」設計判断だが、結果として **logging infra の障害が application の障害になる**。
代替: pull 型 promtail + json-file driver で完全分離 (Lane S-1 で対応中)。

### 教訓 3: 監視 infra 自身の監視が必要 (catch-22 回避)

Loki が死ぬと、Loki 経由でログを集める promtail の error も Loki 経由で集めることになり、
Loki 死亡を Loki ログから検出できない。Loki の `/ready` を Loki 経由ではない別の手段
(例: external healthcheck cron + Slack webhook) で監視する。

---

**Lane B-4 完了**
