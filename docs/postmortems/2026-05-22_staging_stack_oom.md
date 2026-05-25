# Postmortem: 2026-05-22 Staging Stack OOM 全滅

**発生日時**: 2026-05-22 (詳細時刻は VPS journal 要確認 — §Open Questions)
**検出日時**: 2026-05-22 朝 (Slack alert 経由)
**影響範囲**: staging stack 全コンテナ消失 (postgres / loki / promtail / nginx / frontend / backend-blue / backend-green)
**重大度**: P0 (Tier S) — Asana 1215010398340429 [Tier S][CRITICAL-0]
**ステータス**: 解消済 (PR #376 / #377 / #380 で恒久対策)
**関連 Asana**: postmortem RCA タスク, [Tier S] staging frontend build 失敗 (1215000484642381)

---

## 1. 事象概要

2026-05-22 朝、staging stack (`docker-compose.staging.yml` 配下 7 サービス) が **全コンテナ消失** していた。`docker ps` で staging 関連コンテナが 0 件。production stack は無事 (異なるホスト/compose ファイルではないが、staging-watchdog の作用範囲外だった)。

直接トリガーは Next.js frontend build による **ホスト側 OOM**。docker container mem_limit は **frontend をホストプロセスとして実行する build を制約できない**。

---

## 2. タイムライン

> 細かい時刻は staging VPS の `journalctl` / `dmesg -T` 要確認 (dev VPS からは取得不可)。以下は git commit と PR merge 時刻から再構成。

| 時刻 (JST) | 事象 | ソース |
|---|---|---|
| 〜 5/22 朝 | staging stack 通常稼働 | (前日 commit) |
| 5/22 朝 | OOM killer 発火 → staging stack 全消失 | dmesg (要確認) |
| 5/22 朝 | staging-watchdog (5min cron) 復旧試行 → `docker compose up -d` で frontend build 誘発 | scripts/staging-watchdog.sh 旧版 |
| 5/22 朝 | build が前回完了前に次の cron が起動 → **多重 build → OOM 螺旋** | cron + flock 不在 |
| 5/22 10:11 JST | PR #376 (`fix/watchdog-no-build-guard`) merge | `fc1eddf` |
| 5/22 10:11 JST | PR #377 (`fix/staging-mem-limits-oom`) merge | `7473542` |
| 5/22 朝-昼 | staging stack 復旧 | (人手 deploy) |
| 5/22 後 | PR #380 (CF Pages 移行設計) merge — 恒久対策 | `d982688` |

> **Open Question**: OOM 初回発火時刻と回数。次回 drill で `journalctl -u docker` / `dmesg -T` 取得手順を確立する。

---

## 3. 影響

| 項目 | 影響 |
|---|---|
| Production | なし (別 compose / 別 watchdog 対象外) |
| Staging UAT | 朝〜昼 完全停止 (UAT 動線監視 = Stream 8 の対象外時間) |
| データ損失 | なし (postgres backup は前夜 03:00 取得済) |
| 監視 | Slack #ops に OOM 通知後、staging-watchdog の再試行ループが追加ノイズ |
| ユーザー影響 | なし (staging はテスター用、本番ユーザーは production stack 経由) |

---

## 4. Root Cause Analysis

### 4.1 直接原因
- **frontend Next.js build (host process) がホスト RAM 7.6GB を消費し OOM killer 発火**
- swap が無いため OOM killer が即時に container を強制終了

### 4.2 増幅要因 (OOM 螺旋)

`scripts/staging-watchdog.sh` (5min cron) の設計欠陥:

| # | 欠陥 | 結果 |
|---|---|---|
| ① | `flock` による多重起動ガード無し | 前回 cron 走行中に次が重なる |
| ② | `docker compose up -d` を `--no-build` 無しで実行 | image 欠落時に build を誘発 |
| ③ | image 存在チェック無し | 欠落判定で fail-fast できない |

結果として、OOM で frontend image が消えた → watchdog が rebuild → build がさらに RAM を食う → 次の watchdog がさらに rebuild → ... の螺旋。

### 4.3 守備層の弱さ
- **個別 service の `mem_limit` 未設定** (backend-blue/green のみ 768m、postgres/loki/promtail/nginx/frontend は unlimited)
- 単一 service の暴走 → カーネル OOM killer が他 service も巻き添え
- **memswap_limit 未設定** → swap 経由の予測不能挙動の余地 (本件では swap なしのため未顕在化)

### 4.4 構造的要因
- frontend build を **本番/staging VPS 上で実行する設計**自体が、メモリ 7.6GB ホストには過大
- CF Pages 移行設計 (PR #380) が未着手だった

---

## 5. 対応 (実施済)

| 対応 | PR | 内容 |
|---|---|---|
| watchdog 螺旋遮断 | #376 | `flock` + image 存在ガード + `--no-build` |
| 個別 mem_limit 付与 | #377 | postgres 512m / loki 384m / promtail 128m / nginx 64m / frontend 512m (backend 据置 768m)、memswap_limit=mem_limit |
| 恒久対策設計 | #380 | frontend build を Cloudflare Pages に切出し (VPS から build 消失) |

---

## 6. Lessons Learned

1. **自動復旧の責務は最小に**。Watchdog は「既存 image のコンテナ再起動」のみ。build や image fetch は別フローに分離する (PR #376 設計)。
2. **軽量 sidecar (promtail / nginx) でも mem_limit は必須**。「軽い」と「OOM 巻き添え可能性ゼロ」は別。
3. **Cron は flock で多重起動を物理ガード**。スクリプト内ロジックだけでは不十分。
4. **container の mem_limit は host build process を守らない**。build はホスト隔離 (CF Pages / 別 build host) で外す。
5. **swap 無し host は OOM 即死。** 「予測可能な OOM」と「巻き添え連鎖の最小化」は別問題。両方の設計が必要。
6. **Postmortem 再構成は git+PR history で可能** だが、`dmesg -T` / `journalctl` を即時取得する手順 (P0-1 backup_restore_runbook §1 の隣に並ぶ "incident snapshot" runbook) が不在。次の Action Item。

---

## 7. Action Items

| # | アクション | Owner | 期日 | 状態 |
|---|---|---|---|---|
| 1 | PR #380 CF Pages 切出し 実装 (W3 影響範囲外、別 PR) | hkobayashi | 2026-06-01 (Asana SCALE-A2) | 進行中 |
| 2 | staging-watchdog cron 再有効化 (#376 反映後) | on-call | 2026-05-25 (5/22 から 3日) | 要確認 (実機) |
| 3 | production stack にも mem_limit 同等設定を検証 (`docker-compose.production.yml`) | hkobayashi | 2026-05-30 | 未着手 |
| 4 | "Incident snapshot" runbook 作成 (`dmesg -T`, `journalctl`, `docker events` を 1 コマンドで保全) | hkobayashi | 2026-06-05 | 本 postmortem 由来 (NEW) |
| 5 | OOM 初回発火時刻 / 回数を staging VPS から取得 → 本 postmortem §2 を埋める | on-call | 2026-05-26 | Open Question |
| 6 | `mem_limit` 値の妥当性確認 (実測 max RSS との対比) | hkobayashi | 2026-06-15 | 未着手 |

---

## 8. Open Questions

- OOM 初回発火時刻と発火回数 (staging VPS の `dmesg -T`/`journalctl` 確認)
- frontend build がいつから RAM を 7.6GB 超まで消費していたか (回帰 commit の特定)
- staging-watchdog の cron が 5/22 朝に何回起動したか
- 同じ構造 (build on host) で production も将来 OOM するか — 現状 production frontend は CF Pages 移行待ちで同じ脆弱性あり

---

## 関連

- PR #376 `fix/watchdog-no-build-guard` — watchdog 螺旋遮断
- PR #377 `fix/staging-mem-limits-oom` — mem_limit 付与
- PR #380 — CF Pages 切出し設計 (恒久対策)
- Asana 1215010398340429 [Tier S][CRITICAL-0] staging-new 全コンテナ消失 復旧
- Asana 1215028729779736 postmortem: staging stack OOM 消滅 (2026-05-22 RCA) — 本ドキュメント
- `docs/postmortems/2026-05-19_production_stack_container_loss.md` — 前週の類似事象 (production)
- `docs/ops/backup_restore_runbook.md §1` — backup から復旧する場合の手順
