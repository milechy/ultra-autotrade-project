# 自動復旧スコープ設計 v1

**作成日**: 2026-05-18  
**対象**: Ultra AutoTrade 本番環境 (Hetzner VPS)  
**前提**: 1人プロジェクト (hkobayashi) — 深夜 22:00-06:00 は対応者不在  
**関連スクリプト**: `scripts/healthcheck_l1_l6.sh` (L1-L6 検知)、`scripts/auto_recovery.sh` (本ドキュメントの実装先)  
**関連 postmortem**: `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` (nginx IP 固着 → 3h23m 復旧不在)

---

## 設計方針

「対応者不在 = 警告無視と同じ」(PR #248 教訓) への対策として、
単純かつ可逆な障害を自動復旧し、人間判断が必要なものは Pushover で確実に起こす。

**自動復旧の原則:**
1. 可逆性 — 自動アクションは `docker restart` / `docker reload` レベルに限定。データ変更・コード変更・設定変更は行わない
2. 冪等性 — 同じ操作を繰り返しても副作用が出ない操作のみ許可
3. クールダウン — 同一対象を1時間に3回 restart したら停止して人間を呼ぶ (alert fatigue 対策)
4. ログ完全記録 — 何を・いつ・なぜ実行したかを `~/.claude-uata/logs/auto_recovery.log` に記録
5. 非介入原則 — Aave / postgres / DB データ / コード には触れない

---

## 自動復旧する範囲 (AUTO-RECOVERABLE)

### AR-1: nginx upstream IP 固着 → `docker restart nginx`

| 項目 | 内容 |
|------|------|
| **検知** | L1 FAIL + 内部 `/health` 200 + 外形 `/health` non-200 |
| **原因** | frontend-only deploy 後に backend が recreate され nginx が古い IP にプロキシし続ける |
| **自動アクション** | `docker restart ultra-autotrade-nginx-production` |
| **検証** | restart 後 30 秒以内に外形 `/health` 200 |
| **クールダウン** | 1時間に3回まで。3回到達で Pushover priority=2 |
| **参照** | `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` |

**実装メモ**: 内部 `127.0.0.1:8010/health` が 200 で外形が non-200 の場合のみ nginx restart を試みる。
backend 自体が死んでいる場合はこのパターンに合致しないため過剰な restart は起きない。

### AR-2: backend コンテナ unhealthy → `docker restart backend`

| 項目 | 内容 |
|------|------|
| **検知** | L1 FAIL + `docker inspect --format='{{.State.Health.Status}}'` が `unhealthy` または `exited` |
| **原因** | OOM killer / uvicorn ワーカー異常終了 / 一時的 exception ループ |
| **自動アクション** | `docker restart ultra-autotrade-backend-production` |
| **検証** | restart 後 60 秒以内に内部 `/health` 200 + `scheduler_healthy: true` |
| **クールダウン** | 1時間に3回まで。3回到達で Pushover priority=2 |
| **除外** | postgres が死んでいる場合は AR-2 を実行しない (L1 FAIL で postgres チェック先行) |

### AR-3: scheduler dead → backend soft-reload

| 項目 | 内容 |
|------|------|
| **検知** | L2 FAIL (scheduler_healthy=false または last_judgment_age > 60分) かつ backend コンテナは Up |
| **原因** | scheduler loop が例外でクラッシュしたが uvicorn プロセスは生きている |
| **自動アクション** | `docker restart ultra-autotrade-backend-production` (soft restart で scheduler loop 再起動) |
| **検証** | restart 後 90 秒以内に L2 PASS |
| **クールダウン** | 1時間に2回まで (重要度が高いため閾値を下げる)。2回到達で Pushover priority=2 |

### AR-4: cloudflared コンテナ exited → `docker restart cloudflared`

| 項目 | 内容 |
|------|------|
| **検知** | L1 FAIL + 外形 `/health` non-200 + `docker inspect cloudflared` が `exited` |
| **原因** | Cloudflare Tunnel 側の一時的切断・SIGKILL |
| **自動アクション** | `docker restart ultra-autotrade-cloudflared-production` |
| **検証** | restart 後 60 秒以内に外形 `/health` 200 |
| **クールダウン** | 1時間に3回まで。3回到達で Pushover priority=2 |

---

## Phase 2 拡張提案 (P0-B-4 / 2026-05-25 追記)

> 「1 人プロジェクト前提の自動復旧範囲最大化」(Asana B-4) を満たすための追加スコープ案。
> 各 AR-N は **別 PR で個別に実装**する想定 (auto_recovery.sh は本番稼働中のため小さく追加)。

### AR-5 (proposed): frontend コンテナ hang → `docker restart frontend`

| 項目 | 内容 |
|------|------|
| **検知** | frontend `/api/health` (静的) または `/` GET が 60 秒以内に応答しない、かつ container は Up |
| **原因** | Node.js GC スパイク / hot-reload 残骸 / ファイル descriptor 枯渇 |
| **自動アクション** | `docker restart ultra-autotrade-frontend-production` |
| **検証** | restart 後 90 秒以内に `/` 200 |
| **クールダウン** | 1時間に3回まで |
| **理由** | `restart: always` は **クラッシュ**は救うが **hang** は救わない |

### AR-6 (proposed): promtail / loki スタックの自動復旧

| 項目 | 内容 |
|------|------|
| **検知** | promtail が Loki に push 失敗を 10 分連続 (Loki down) |
| **原因** | Loki OOM、disk 枯渇、index 破損 |
| **自動アクション** | `docker restart ultra-autotrade-loki-production` (1 回のみ) → 失敗時 HR エスカレ |
| **検証** | promtail metrics で push 成功 |
| **クールダウン** | 1時間に1回 (慎重) |

### AR-7 (proposed): postgres replication lag (将来)

| 項目 | 内容 |
|------|------|
| **検知** | replica lag > 60s (SCALE-B3 PostgreSQL replica 導入後) |
| **自動アクション** | replica restart は **しない** (HR エスカレ) — data 整合性優先 |
| **理由** | プロトタイプ段階。実装は SCALE-B3 完了後 |

### Runtime 配信 (本 PR で systemd template 追加)

外部 cron / systemd timer から 5 分間隔で `auto_recovery.sh --check-all` を起動する。

| ファイル | 役割 |
|---|---|
| `infra/systemd/ultra-autotrade-auto-recovery.timer` | 5 分間隔 trigger |
| `infra/systemd/ultra-autotrade-auto-recovery.service` | one-shot 実行 unit。default `DRY_RUN=true` (観察期間用) |

**本番反映 (人間タスク)**:
```bash
sudo cp infra/systemd/ultra-autotrade-auto-recovery.{timer,service} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ultra-autotrade-auto-recovery.timer
# 観察 1 週間後、DRY_RUN=false にする (/etc/default/ultra-autotrade-auto-recovery を作成)
```

---

## 自動復旧しない範囲 (HUMAN-REQUIRED)

以下はいずれも「人間の判断が必要」または「自動アクションが状況を悪化させるリスクが高い」。
自動復旧は行わず、Pushover で hkobayashi を起こす。

### HR-1: postgres コンテナ異常

| 理由 | 詳細 |
|------|------|
| **SIGKILL ループ** | 2026-05-17 インシデント: postgres が 2,448 回クラッシュ。`docker restart` では解決しない。WAL 損傷 / OOM / disk 枯渇の根本原因調査が必要 |
| **データ整合性リスク** | postgres restart 中に未フラッシュの WAL が残る場合あり。automated restart はデータロスを助長する可能性 |
| **backup 確認必須** | 復旧前に `docs/31_backup_restore_procedures.md` に従い backup 取得・確認が必要 |
| **Pushover** | priority=2 (深夜でも起こす) |

### HR-2: Aave operation 失敗

| 理由 | 詳細 |
|------|------|
| **資金安全性** | HF < 1.6 の HARD_STOP は自動復旧で解除しない (OR ロジック、`docs/33_emergency_stop_governance.md` §2) |
| **RPC 障害** | RPC URL の変更・切替は `.env.production` 変更を伴い Tier S 操作 |
| **Pushover** | priority=2 |

### HR-3: 本番 DB スキーマ破損

| 理由 | 詳細 |
|------|------|
| **不可逆** | テーブル・カラムの損傷は `docker restart` で復旧しない |
| **バックアップ照合必須** | `docs/31_backup_restore_procedures.md` §3 の pg_restore 手順が必要 |
| **Pushover** | priority=2 |

### HR-4: 複数コンテナ同時 down (3個以上)

| 理由 | 詳細 |
|------|------|
| **連鎖障害の可能性** | ネットワーク分離・OOM・disk 枯渇 等の全体障害。個別 restart では解決しない |
| **対処** | `healthcheck_l1_l6.sh` の L1 containers_running < 5 で Pushover priority=2 |
| **Pushover** | priority=2 |

### HR-5: disk 使用率 > 85%

| 理由 | 詳細 |
|------|------|
| **根本解決必要** | `docker system prune -af` は使用中イメージを削除するリスク (CLAUDE.md 絶対禁止)。週次 `docker_cleanup.sh` の手動確認が必要 |
| **Pushover** | priority=1 (High) — 急ぐが深夜に起こすほどではない。朝確認可 |

### HR-6: AI 判定 24h 件数ゼロ (L3 FAIL) かつ scheduler_healthy=true

| 理由 | 詳細 |
|------|------|
| **設計バグの可能性** | scheduler は生きているが判定が出ていない = コード・設定の問題。restart では解決しない |
| **Pushover** | priority=1 (High) |

### HR-7: nginx / cloudflared クールダウン上限到達

| 理由 | 詳細 |
|------|------|
| **ループ検出** | 1時間に N 回 restart しても復旧しない = 根本原因が别にある |
| **Pushover** | priority=2 |

---

## 復旧トリガー設計

```
healthcheck_l1_l6.sh (5分cron, Hetzner)
    │
    ├── L1 FAIL
    │   ├── postgres exited → [HR-1] Pushover priority=2
    │   ├── コンテナ 5個未満 → [HR-4] Pushover priority=2
    │   ├── 内部200 + 外形non-200
    │   │   ├── cloudflared exited → [AR-4] docker restart cloudflared
    │   │   └── nginx 問題の可能性 → [AR-1] docker restart nginx
    │   └── backend unhealthy/exited → [AR-2] docker restart backend
    │
    ├── L2 FAIL (scheduler dead)
    │   └── backend Up かつ scheduler_healthy=false → [AR-3] docker restart backend
    │
    ├── L3 FAIL かつ L2 PASS
    │   └── [HR-6] Pushover priority=1
    │
    └── クールダウン上限到達
        └── [HR-7] Pushover priority=2 + 自動復旧停止

auto_recovery.sh (healthcheck_l1_l6.sh から呼び出し)
    │
    ├── クールダウンカウンタ確認 (ファイルベース、~/.claude-uata/recovery-cooldown/)
    ├── 復旧アクション実行
    ├── 検証 (30-90秒待機 → curl/docker inspect)
    ├── ログ記録 (~/.claude-uata/logs/auto_recovery.log)
    └── Slack 通知 (#ultra-auto-project)
```

---

## クールダウン仕様

| 対象 | 1時間あたりの最大 restart 回数 | 上限到達時の動作 |
|------|-------------------------------|-----------------|
| nginx | 3 | Pushover priority=2 + 自動復旧停止 |
| backend | 3 | Pushover priority=2 + 自動復旧停止 |
| cloudflared | 3 | Pushover priority=2 + 自動復旧停止 |
| scheduler (backend経由) | 2 | Pushover priority=2 + 自動復旧停止 |

**クールダウンカウンタのリセット**: 
- 1時間のスライディングウィンドウ (現在時刻 - 1h 以前のエントリを削除)
- 手動リセット: `rm ~/.claude-uata/recovery-cooldown/<container>-*.ts`

---

## Pushover priority=2 発火条件 (docs/24h-automation-runbook.md §Pushover 優先度マッピング の補強)

priority=2 (Critical / 深夜でも電話呼出 / retry=60 expire=3600) を発火する条件:

| 状況 | 検知元 | 備考 |
|------|--------|------|
| 本番 /health (外形) 5分連続 non-200 | uata-supervisor.sh | 既存 |
| postgres コンテナ exited / SIGKILL ループ | auto_recovery.sh | **新規** |
| 複数コンテナ同時 down (3個以上) | auto_recovery.sh | **新規** |
| nginx/backend/cloudflared クールダウン上限 (1h に N 回 restart) | auto_recovery.sh | **新規** |
| Aave HARD_STOP 発動 (HF < 1.6) | backend scheduler | 既存 (MonitoringService) |
| mainnet wallet 不正操作試行 | backend security layer | 既存 |
| DB スキーマ破損検知 | auto_recovery.sh | **新規** (L1 FAIL + psql 接続不可) |

priority=1 (High / 目立つが深夜は起こさない) を発火する条件:

| 状況 | 検知元 | 備考 |
|------|--------|------|
| disk 使用率 > 85% | auto_recovery.sh or healthcheck | **新規** |
| AI 判定 24h 件数ゼロ (L3 FAIL) かつ scheduler 生存 | auto_recovery.sh | **新規** |
| UATa タスク 3件以上連続 failed (2h 内) | uata-supervisor.sh | 既存 |
| Tier S 承認待ち | uata-supervisor.sh | 既存 |

---

## 今後の実装計画 (別 Tier S タスク)

本ドキュメントはあくまで **設計** である。
実際に Hetzner 本番環境へ配置・cron 登録するには以下の Tier S 操作が必要:

1. `scripts/auto_recovery.sh` を Hetzner に配置 (`/opt/ultra-autotrade/scripts/`)
2. `scripts/healthcheck_l1_l6.sh` を更新して `auto_recovery.sh` を呼び出す
3. Hetzner cron に `*/5 * * * *` でヘルスチェック + 自動復旧を登録
4. `~/.claude-uata/recovery-cooldown/` ディレクトリ作成 (Hetzner 上)
5. 動作確認: `DRY_RUN=true bash scripts/auto_recovery.sh` で空振りテスト

**Tier S 理由**: `scripts/healthcheck_l1_l6.sh` および cron 設定は本番インフラ変更のため。
実装は別日に Opus モデルで Tier S シリアル実行する。

---

## 参照

- `docs/15_rollback_procedures.md` — ロールバック手順
- `docs/33_emergency_stop_governance.md` — 緊急停止ガバナンス
- `docs/24h-automation-runbook.md` — 24h 自動化 Pushover 優先度マッピング
- `scripts/healthcheck_l1_l6.sh` — L1-L6 ヘルスチェック実装
- `scripts/uata-pushover-notify.sh` — Pushover 通知関数
- `scripts/uata-supervisor.sh` — stuck 検出 + rollback supervisor
- `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` — nginx IP 固着インシデント
