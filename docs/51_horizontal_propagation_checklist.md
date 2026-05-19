# 同型バグ 水平展開チェックリスト

> 生成: 2026-05-19 / 背景: 2026-05-01 production hotfix (PR #163) が staging に横展開されず、
> 2026-05-09 に同型 502 が 12 日遅延検出された (postmortem: docs/postmortems/2026-05-09_staging_api_502.md)。
> production hotfix PR をマージ・クローズする前に必ず本チェックリストを完了する。

---

## 対象シナリオ

本チェックリストは以下のいずれかに該当する変更で実行する:

- **インフラ変更**: nginx port・cloudflared ingress・docker-compose ports・upstream.conf 変更
- **セキュリティ修正**: 認証・CORS・CSP・env ファイルに関わる修正
- **バックエンド API パス変更**: エンドポイントパス・バージョンプレフィックス変更
- **production hotfix**: staging で発生していない問題を production のみで修正した場合

---

## チェックリスト (PR close 前に完了)

### A. 同型リスク確認

- [ ] **対称環境確認**: この修正は production にのみ適用した。staging で同型問題が発生していないかを確認したか
  - 確認方法: `bash scripts/env_drift_check.sh` を実行し警告・差異なしを確認
  - staging に同型問題が存在する場合: **A-2 以降を続行する**
  - staging に同型問題がない場合: **B に進む**

- [ ] **A-2 staging 修正 PR 起票**: staging 向けの hotfix PR を作成したか（同日中）
  - PR description に「production #NNN の staging 水平展開」と明記する
  - Asana タスクを作成して本 PR に紐付ける

- [ ] **A-3 水平展開完了確認**: staging 修正 PR がマージされたか（当週中）
  - production PR の description に「staging 水平展開: PR #NNN マージ済」を記載する

### B. インフラ変更時の追加確認

インフラ変更（nginx/cloudflared/compose/upstream）が含まれる場合のみ実行:

- [ ] **B-1 drift check 実行**: `bash scripts/env_drift_check.sh` が 0 件 drift でパスするか確認
- [ ] **B-2 port 一覧確認**: 変更した port を参照している全箇所を更新したか

  | 変更内容 | 確認が必要な箇所 |
  |---|---|
  | nginx 公開 port 変更 | cloudflared config.yml / Dashboard ingress / docs |
  | cloudflared ingress port 変更 | nginx compose ports / 外形 healthcheck |
  | backend 内部 port 変更 | nginx upstream.conf / deploy_production.sh |
  | frontend port 変更 | cloudflared config.yml / nginx location |

- [ ] **B-3 staging への追従**: 同じ変更を staging compose / upstream.conf に反映したか

### C. デプロイ後確認

- [ ] **Gate 8 外形確認**: 変更後に外形 `/health` を 5 回連続確認

  ```bash
  # production
  for i in 1 2 3 4 5; do
    curl -sf -o /dev/null -w "[%{http_code}] " https://api.ultra-auto-trade.com/health
    sleep 2
  done; echo

  # staging (CF Access トークン使用)
  for i in 1 2 3 4 5; do
    curl -sf -o /dev/null -w "[%{http_code}] " \
      -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
      -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
      https://api-staging.ultra-auto-trade.com/health
    sleep 2
  done; echo
  ```

---

## drift check スクリプト実行

```bash
# 手動実行（差異確認のみ）
bash scripts/env_drift_check.sh

# Slack 通知付き（CI から呼ぶ際）
bash scripts/env_drift_check.sh --slack

# 差異ありのみ出力
bash scripts/env_drift_check.sh --quiet
```

自動実行: `.github/workflows/drift_check.yml` が毎日 02:00 JST に実行する。

---

## よくある drift パターン

| パターン | 発生条件 | 影響 |
|---|---|---|
| cloudflared ingress port 古い | nginx port 変更後に Dashboard 更新漏れ | 502 (外部経路断絶) |
| upstream.conf 旧形式残存 | `set $backend` への移行漏れ | nginx 再起動後に IP 固着 502 |
| staging compose port 古い | production port 変更後の横展開漏れ | staging port 衝突・502 |
| env ファイル drift | `sed -i` 一括更新で両環境が同値に | 環境分離崩壊 (セキュリティ違反) |

---

## 参照

- `scripts/env_drift_check.sh` — 自動 drift 検知スクリプト
- `.github/workflows/drift_check.yml` — 毎日 02:00 JST 自動実行
- `docs/postmortems/2026-05-09_staging_api_502.md` — cloudflared ingress port mismatch 12 日遅延検出 RCA
- `docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md` — nginx upstream IP 固着 RCA
- `CLAUDE.md §2026-05-09追加` — インフラ変更チェックリスト 鉄則 4
