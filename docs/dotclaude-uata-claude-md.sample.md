# ~/.claude-uata/CLAUDE.md サンプル

> Mac で `CLAUDE_CONFIG_DIR=~/.claude-uata claude` 起動時に auto-inject されるルールファイルのリポジトリ管理サンプル。
> 実体は `~/.claude-uata/CLAUDE.md`（mode 600）。secrets は含めないこと。
>
> 3層運用の詳細: `CLAUDE.md §開発環境 v3` / `docs/20_development_vps_setup.md` 参照。

---

## このセッションでできること（許可リスト）

| 操作 | 具体例 |
|------|--------|
| Asana 読み書き | 朝プロトコル / タスク更新 / Phase 計画 |
| docs 編集 | CLAUDE.md / docs/*.md の確認・更新 |
| Agent View 起動 | `claude agents` でレーン一覧確認 |
| morning-report 実行 | `scripts/uata-morning-report.sh` |
| asana-poll 実行 | `scripts/uata-asana-poll.sh` |
| ローカル git 操作 | merge / push / PR 作成 |
| dev VPS 接続 | `ssh uata-assistone-dev`（下記参照、2026-07-02時点で未構築） |

---

## 禁止操作（このセッションから行ってはならないこと）

| 禁止 | 理由 |
|------|------|
| production VPS (`5.223.88.14`) への直接 ssh | 3段プロトコル経由のみ（CLAUDE.md ABSOLUTE、alias自体を作らない） |
| dev VPS への直接 IP 接続 | 必ず `ssh uata-assistone-dev` alias を使う |
| `.env.production` の直接編集 | guard-env-files.sh フック対象 |
| `deploy_production.sh` の手動実行 | production VPS 上で実行すること |
| 山本さん DM | 本人が送信すること |
| secrets / API キーの commit | .env ファイルは絶対コミットしない |

---

## dev / staging VPS 接続方法（2026-07-02 ASSIST ONE移行後）

```bash
# dev VPS (95.216.167.198、2026-07-02時点 provisioning のみ・アプリ環境未構築)
ssh uata-assistone-dev
# → Mac ~/.ssh/config で alias 定義済（root@95.216.167.198 / ~/.ssh/hetzner_assistone_stagingdev）

# staging VPS (188.34.167.142、staging+staging-v4 同居)
ssh uata-assistone-staging
# → Mac ~/.ssh/config で alias 定義済（root@188.34.167.142 / ~/.ssh/hetzner_assistone_stagingdev、dev と鍵共用）

# production VPS (5.223.88.14) — 3段プロトコル経由のみ、alias自体を作らない
# @phase1-investigator / @phase3-deployer を使うこと
```

旧VPS(77.42.46.155、旧dev VPS uata-dev-01=77.42.79.75)は移行に伴い廃止対象
（旧production/stagingは保険期間3〜7日経過後に解約予定）。

---

## 朝プロトコル §9 Step 0（このセッションで必須）

claude.ai セッションを開く前に CLI で正本確認:

```bash
cd ~/projects/ultra-autotrade
git fetch origin && git log origin/main --oneline -5
for f in CLAUDE.md docs/14_test_strategy.md docs/ops/01_api_endpoints.md; do
  echo "=== $f ===" && git log -1 --format="%h %ci %s" -- "$f"
done
```

Step 0 完了確認なしに claude.ai §9 を進めることを禁止する（鉄則8違反）。

---

## セットアップ手順

```bash
# 1. このサンプルを実体ファイルとしてコピー
cp docs/dotclaude-uata-claude-md.sample.md ~/.claude-uata/CLAUDE.md

# 2. 権限を 600 に設定
chmod 600 ~/.claude-uata/CLAUDE.md

# 3. 動作確認（claude-uata セッションで auto-inject されるか）
CLAUDE_CONFIG_DIR=~/.claude-uata claude --print "このセッションのルールを要約して"
```

---

## 参照

- `CLAUDE.md` §開発環境 v3 — 3 層運用（dev / staging / production）
- `CLAUDE.md` §朝プロトコル §9 — Step 0 強制化ルール（PR #246）
- `docs/20_development_vps_setup.md` — dev VPS 詳細手順（PR #256）
