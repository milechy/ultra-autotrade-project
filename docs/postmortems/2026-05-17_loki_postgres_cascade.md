# Postmortem: Loki 半死状態による logging-driver カスケードと無検知放置

| 項目 | 値 |
|---|---|
| 発生日時 | 2026-05-15 〜 2026-05-17 (production / Loki 半死状態の継続区間) |
| 直接影響日 | 2026-05-17 早朝 (今朝の事故。Loki 半死が直接原因) |
| 検出 | 2026-05-17 午前11時頃 — Lane B-4 手動調査で Loki `/ready` = 503 を発見 (自動検知ゼロ) |
| 復旧 | 2026-05-17 06:49:40 UTC — Loki container が compose recreate により**偶発的に**自己回復 |
| 確定検証 | 2026-05-18 02:00 頃 — Lane B-4 が実 push/query + promtail ライブ取り込みで完全復旧を実証 |
| 影響範囲 | production 全サービス (postgres / backend-blue / backend-green / nginx / frontend) の Docker ログ送出経路。Loki への push が `empty ring` で 500 になる区間、`logging: driver: loki` 経由のログ書込が滞留 |
| Severity | P1 (ログ可観測性の全損 + RC-2: 死亡を誰も検知できない構造欠陥) |
| Owner | claude.ai (PM) + Claude Code Lane B-4 (調査・RCA / Opus 4.7) |
| 関連 Lane | Lane S-1 (logging driver json-file 切替) / Lane S-2 (backup_db.sh) — 本 PR スコープ外 |

## TL;DR

production の全アプリサービスが `docker-compose.production.yml` で `logging: driver: loki`
(Loki Docker logging plugin / blocking 送出) を使用している。2026-05-15 〜 17 にかけて
`ultra-autotrade-loki-production` (grafana/loki:2.9.0, single-binary) が
**ingester ring 未登録 → `/loki/api/v1/push` が HTTP 500 `empty ring` を返す半死状態**
に陥り、`/ready` が 503 を返し続けた。Loki container 自体は `Up` のままだったため
`docker ps` では正常に見え、**healthcheck も外形監視も存在しなかったため約2日間誰も検知できなかった**
(RC-2)。これが「今朝の事故」の直接原因。

Loki は 2026-05-17 06:49:40 UTC に **compose recreate (Lane S-1 等の `docker compose up -d`
に伴う巻き込み recreate)** が走ったことで ingester が ring に再登録され、
**偶発的に自己回復**した。以降 19 時間以上ノーエラー、`/ready` 5/5 200、
実 push→query 成功、promtail のライブ取り込み継続を確認済み。

復旧は意図的な対処ではなく偶然であり、根本対策 (Loki 死亡の検知手段) は未実装。
本 postmortem で再発防止策を P0/P1 で定義する。

## タイムライン (UTC)

| 時刻 | 事象 |
|---|---|
| 2026-05-14 07:33:30 | 旧 Loki container Created (この世代が後に半死化) |
| 2026-05-15 07:31〜08:18 | Loki 起動 warn 連発 (`global timeout not configured` / `fifocache deprecated`)。08:17:58 `scheduler_processor` `context canceled` 多発 |
| 2026-05-15 08:18:20 | Loki 起動ログ末尾。以後この世代は半死状態 (`/ready` 503 / push 500 `empty ring`) |
| 2026-05-15 〜 17 | 約2日間、Loki 半死を**誰も検知できず放置** (RC-2)。`docker ps` は `Up` 表示のまま |
| 2026-05-17 06:44:37 | promtail → Loki push が `500 ... empty ring` (ingester ring が空)。直後 `dial tcp: lookup loki ... server misbehaving` (recreate 中の DNS 断) |
| 2026-05-17 06:48:13 | promtail 最終 warn ログ(DNS 断)。以後 promtail は無音 (= 送信成功) |
| 2026-05-17 06:49:40 | Loki container が **compose recreate**。新世代起動。ingester が `127.0.0.1:9096` で ring に ACTIVE 登録 |
| 2026-05-17 06:49:40 以降 | Loki ノーエラー (log_level: warn のため成功時無音)。半死から偶発回復 |
| 2026-05-17 ~02:00(午前11時 JST) | Lane B-4 が手動調査開始。`/ready` 503 (調査初回時点の観測) → 精査で既に `ready` に回復済みと判明 |
| 2026-05-18 01:55〜02:00 | Lane B-4 が完全復旧を実機実証 (下記「復旧確認の実機証跡」) |

> 注: 「今朝(5/17)午前11時時点」のタスク前提では Loki `/ready`=503 だったが、
> Lane B-4 精査時点では 06:49:40 の recreate により既に `ready` へ回復していた。
> 503 観測は半死世代 (〜06:49) または recreate 直後の transient 窓を見ていた可能性が高い。

## 真因 (Root Cause)

### RC-1 (一次原因): Loki single-binary の ingester ring 未登録 → `empty ring`

`grafana/loki:2.9.0` を single-binary (all-in-one) で運用。`docker/loki/loki-config.yaml` は
`common.ring.kvstore.store: inmemory` / `common.ring.instance_addr: 127.0.0.1` /
`replication_factor: 1`。inmemory ring + single instance 構成では ingester が自プロセスの
ring に自己登録して初めて distributor が push を受理できる。半死世代では
**ingester が ring 登録を完了できず distributor が `empty ring` で全 push を 500 拒否**
した (push 経路の全損)。`scheduler_processor` の `context canceled` 連発と
起動 warn 直後のログ停止は、内部モジュール初期化が途中で失敗/停止していた兆候。

2.9.0 は古い patch (build 2023-09-07, revision 2feb64f6) であり、single-binary の
ring/初期化に関する既知の不安定挙動を含む系統。本 Lane では web 検索による
特定 issue 断定は行わず「2.9.0 single-binary で再現しうる ring 未登録系の半死」と記述する
(推測で issue 番号を書かない方針)。

### RC-2 (構造欠陥 / 本件の本質): Loki 死亡を誰も検知できない

これが「今朝の事故」を2日間放置させた本質的原因。

1. **`docker-compose.production.yml` の `loki` サービスに `healthcheck:` が無い。**
   そのため Loki が半死でも `docker ps` の STATUS は `Up`。container 健全性 ≠ Loki 健全性。
2. **Loki `/ready` を叩く外形監視 (Gate 8 相当) が存在しない。**
   既存の post-deploy healthcheck は backend `/health` のみで Loki 経路は対象外。
3. **`log_level: warn` のため正常時も半死時も Loki 自身のログがほぼ無音。**
   「ログが出ていない」と「死んでいる」を区別する手段が運用上なかった。
4. **promtail 側のエラーは warn レベルで docker logs に出るが、それを集約・通知する経路が無い**
   (promtail のログ自体も Loki に送られ、Loki が死ぬと自己参照的に失われる)。

### RC-3 (カスケード機構): 全サービスが blocking な `driver: loki` を使用

`docker-compose.production.yml` で postgres / backend-blue / backend-green / nginx / frontend
の全てが `logging: driver: loki`, `loki-url: http://loki:3100/loki/api/v1/push`,
`loki-retries: "3"`, `loki-timeout: "10s"` を設定。Loki が push を 500 拒否する区間、
Docker daemon のログ送出が retry/timeout を消費し、`loki-postgres-cascade` のファイル名が
示す通り **postgres を含むサービスの stdout/ログ経路に滞留圧**が伝播しうる構成だった。
(Loki driver の blocking 特性 = アプリ可用性と可観測性基盤が密結合)。
→ logging driver の `json-file` 切替は **Lane S-1 のスコープ**であり本 PR では変更しない。

## 復旧確認の実機証跡 (Lane B-4 / 2026-05-18 01:55〜02:00 UTC)

| 検証 | 結果 |
|---|---|
| `GET /ready` 連続5回 | 5/5 `HTTP/1.1 200 OK` + body `ready` (安定) |
| ring メンバー (`/ring`, `/metrics`) | ingester / distributor / compactor / scheduler 全て `ACTIVE`=1。ingester `5e3310d7a2a5` @ `127.0.0.1:9096` registered `2026-05-17T06:49:40Z`、heartbeat 数秒前 |
| 実 push → query | `{job="laneB4-verify"}` を push → 即 query で同一行を取得成功 (distributor→ingester→querier 全経路 OK) |
| promtail ライブ取り込み | 直近10分で `ultra-autotrade-backend-green-production` の実ログを Loki から取得確認。取り込み container に production backend-blue/green/nginx を含む |
| promtail positions.yaml | mtime `2026-05-18 01:57:50` で更新継続 (送信進捗が前進している証跡) |
| Loki / promtail のエラーログ | Loki 最新行 `2026-05-17T06:49:40` 起動 warn、promtail 最新行 `06:48:13` DNS 断 warn。**以後19h+ 無音 = warn レベル運用下では正常稼働を意味する** |
| `/loki` ディレクトリ/権限 | `loki:loki` (uid 10001) 所有、chunks/compactor/wal/tsdb-shipper-* 全て存在。wal mtime 当日更新 (WAL 書込継続)。disk 使用 8.7M / host `/` 45% — 容量問題なし |

→ **DoD「Loki HTTP /ready 200」「30分間 error なし」「promtail ↔ Loki 接続成功」を実機で充足。**
(19h 無音 + 5/5 200 + ライブ取り込みにより 30 分要件は十分に上回る)

## Phase 2/3 判断: 再起動は実施しない (意図的 no-op)

タスクの復旧手順は A(config)/B(WAL詰まり)/C(image更新)/D(restart) の選択だったが、
調査の結果 **Loki は既に完全復旧しており健全**。健全な Loki を `docker restart` すると
RC-1 の半死/`empty ring` transient 窓を再び発生させるリスク (5/17 06:44〜06:49 で実際に
発生したのと同型) があるため、**Phase 3 の再起動・config 変更は実施しないことを意図的判断**
として記録する。docker-compose.production.yml は Tier S かつ Lane S-1 が編集中のため
本 Lane では同ファイルを触らない (鉄則4/Tier 分類遵守)。

## 再発防止策

### P0 (当日〜次デプロイ): Loki 死亡を検知可能にする

1. **`docker-compose.production.yml` の `loki` サービスに `healthcheck:` を追加** (担当: Tier S 直列枠 / Lane S-1 と調整)。
   ```yaml
   healthcheck:
     test: ["CMD", "wget", "-q", "--spider", "http://localhost:3100/ready"]
     interval: 30s
     timeout: 5s
     retries: 5
     start_period: 60s
   ```
   → `docker ps` の STATUS が `unhealthy` を示し、半死を即可視化。
2. **post-deploy / 朝プロトコルに Loki 外形チェックを Gate 8 拡張として追加**。
   ```bash
   docker exec ultra-autotrade-loki-production wget -qO- http://localhost:3100/ready
   # 'ready' 以外 → Slack #ultra-auto-project 通知
   ```

### P1 (次スプリント)

3. **Loki/promtail の死活を朝プロトコル業務サニティに組込**
   (CLAUDE.md「2026-05-13追加 セクション1 策1-2」の Gate 8 SQL と並べて、
   `/ready` 200 + 直近10分の Loki 取り込み 1 件以上を確認)。
4. **logging driver の `json-file` 化** (= RC-3 のカスケード遮断) — **Lane S-1 担当**。
   可観測性基盤 (Loki) とアプリ可用性を疎結合化する。本件と対の根本対策。
5. **Loki version の見直し**: 2.9.0 (2023-09-07 build) は古い。2.9.x 最新 patch への
   更新可否を別 Asana タスクで評価 (single-binary ring 安定性改善の有無を確認)。
6. **promtail のログを Loki 以外にも出す** (json-file 併用 or stderr)。
   Loki 死亡時に promtail のエラーが Loki と共倒れする自己参照問題の解消。

### 既存教訓との接続

- CLAUDE.md「2026-05-12追加」鉄則4「nginx コンテナのログは Loki に取り込む(要追加実装)」
  は本件の RC-3 と同根 (可観測性基盤の単一障害点)。json-file 化 (P1-4) で整理する。
- CLAUDE.md「2026-05-09」Gate 8 (外形 /health) の思想を **Loki `/ready` にも拡張**するのが P0-2。

## 学び

- **`Up` は「生きている」を意味しない。** healthcheck の無い container は「死んでいないこと」しか
  保証しない。可観測性基盤こそ healthcheck と外形監視が必須 (それ自体が監視の前提だから)。
- **偶発回復を「対処済み」と扱わない。** 今回は無関係 Lane の compose recreate が偶然
  ingester を ring 再登録させただけ。根本対策 (検知手段) を入れなければ次も2日放置になる。
- **可観測性基盤とアプリ可用性を密結合させない。** blocking な `driver: loki` は
  「ログ基盤の障害」を「アプリの障害」に昇格させる。json-file 経由 + promtail pull 型が正解。

## 参照

- 調査 Lane: Lane B-4 (Loki 真因調査 + 再起動 / Tier B / Opus 4.7)
- 関連 Lane: Lane S-1 (logging driver json-file 切替), Lane S-2 (backup_db.sh)
- 設定: `docker/loki/loki-config.yaml`, `docker-compose.production.yml` (loki/promtail/各サービス logging)
- 関連教訓: CLAUDE.md「2026-05-09」Gate 8 / 「2026-05-12」鉄則4 / 「2026-05-13」朝プロトコル Gate 8
