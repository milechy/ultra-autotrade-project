# オンコールポリシー（1人プロジェクト / 2026-05-18 策定）

> 2026-05-21 refactor で `CLAUDE.md` から分離。

## 対応時間帯

| 時間帯 | JST | 対応方針 | 連絡手段 |
|---|---|---|---|
| **コアタイム** | 09:00–22:00 | 最優先対応（P0: 30分以内、P1: 2時間以内） | Slack + 電話エスカレーション |
| **ベストエフォート** | 22:00–09:00 | 起床後最優先対応（起床時に確認・対応） | Slack のみ（電話不可） |

- **電話エスカレーション対象**: P0（本番ダウン / 資金リスク / Aave HF < 1.6）のみ
- **Slack 通知**: `#ultra-auto-project` — 全 P0/P1/P2 アラートを集約
- **夜間自動復旧**: Docker `restart: always` + scheduler_watchdog（30 分監視）が第一防衛線。
  自動復旧完了後に Slack 通知が来た場合は、翌朝コアタイムに事後確認で可。

## 自動復旧範囲（`restart: always` コンテナ一覧）

以下のコンテナは Docker Daemon が自動再起動する。手動介入不要（ただしループ再起動は P1 対応）。

| コンテナ名 | 役割 | 備考 |
|---|---|---|
| `ultra-autotrade-postgres-production` | DB | crash → auto restart + pgvector データ保持 |
| `ultra-autotrade-backend-blue-production` | API (Blue) | Blue/Green 片系ダウンは nginx が自動退避 |
| `ultra-autotrade-backend-green-production` | API (Green) | 同上 |
| `ultra-autotrade-nginx-production` | リバースプロキシ | restart 後に upstream IP 固着に注意（docs/postmortems/2026-05-12） |
| `ultra-autotrade-cloudflared-production` | Cloudflare Tunnel | crash → auto restart で外形経路復旧 |
| `ultra-autotrade-frontend-production` | Next.js SSR | crash → auto restart |
| `ultra-autotrade-loki-production` | ログ集約 | 監視基盤。停止中はログ欠損のみ |
| `ultra-autotrade-promtail-production` | ログ収集 | 同上 |

## 夜間アラート受信時の判断フロー

```
Slack アラート受信
  ↓
22:00-09:00 ベストエフォート帯か?
  YES → 「自動復旧済み通知」か確認
         YES → 翌朝コアタイムに事後 RCA で可
         NO (継続障害) → 起床後 P0 対応
  NO (コアタイム) → P0: 30 分以内対応
```

## scheduler_watchdog による自動監視

- 30 分ごとに AI 判定間隔を確認
- `interval_hours * 2` 超過 → Slack `#ultra-auto-project` 通知
- `/health` レスポンスの `scheduler_healthy` フィールドで状態確認可能
