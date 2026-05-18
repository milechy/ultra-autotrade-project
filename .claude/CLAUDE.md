# MUST READ FIRST — CLI Auto-Inject Rules (Ultra AutoTrade)

> `.claude/CLAUDE.md` は Claude Code CLI 起動時に自動 inject される。リポジトリ直下 CLAUDE.md の補完用。

---

## Step 0: 環境確認 (毎セッション冒頭必須)

CLI を起動したら必ず以下を実行して、どの環境で作業しているか確認すること:

```bash
hostname && pwd && echo "branch: $(git branch --show-current 2>/dev/null || echo 'not-git')"
```

### ホスト判定

| hostname / IP | 環境 | 許可 | 禁止 |
|---|---|---|---|
| `uata-dev-01` / `77.42.79.75` | **dev VPS** | git commit / push / merge / Claude Code 実行 | 本番 DB 直接操作 |
| `77.42.46.155` | **production VPS** | git pull / docker compose up / deploy_production.sh | git commit / git merge / nano 直接編集 |
| Mac (`hostname` = 個人 Mac) | **ローカル** | 全開発作業 / Agent View 起動 | 本番 VPS 直接接続（3段プロトコル経由のみ） |

### production VPS での禁止操作 (ABSOLUTE)

```bash
# ❌ 禁止 — production VPS で絶対に実行しない
git commit -m "..."          # Hetzner は pull only
git merge feature/xxx        # ローカル Mac で merge → push → pull
nano /opt/ultra-autotrade/.. # 直接ファイル編集

# ✅ 正しい手順
# ローカル Mac で編集 → git push origin main → Hetzner で git pull origin main
```

---

## ファイル編集ルール (全環境共通)

### sed -i 禁止 → awk + tmpfile + mv を使う

```bash
# ❌ 禁止: sed -i は .env ファイルで前行連結バグを引き起こす
sed -i 's/OLD/NEW/' file.txt
# ✅ 正しい: awk + tmpfile + mv
awk '{gsub(/OLD/, "NEW"); print}' file.txt > /tmp/file_new.txt && mv /tmp/file_new.txt file.txt
# ✅ 環境変数追加は printf で改行を保証
printf '\nKEY=VALUE\n' >> .env.staging
```

---

## 並列開発経路 (2026-05-17 Agent View 標準化)

### 現在の標準経路: Agent View

```bash
# 新規 Lane 起動
claude --bg "<プロンプト>"

# 全 Lane 一覧確認
claude agents
```

### 廃止済み経路 (使わない)

| 経路 | 状態 | 理由 |
|---|---|---|
| `tmux` 5ペイン手動管理 | **廃止** | Agent View で代替 |
| `claude --bg` + `tmux attach` | **廃止** | Agent View で完結 |
| `scripts/uata-dispatch.sh` | **廃止** | queue.db + Lane プロンプト方式に移行済み |

---

## 朝プロトコル §9 Step 0 強制化

→ `CLAUDE.md §9 Step 0` (PR #246) 参照。CLI 起動後 最初の操作は必ず Step 0。

```bash
# Step 0 テンプレ (read-only / 約5分)
cd ~/projects/ultra-autotrade
git log --since="2026-04-15" --oneline -- docs/ | head -20
for f in CLAUDE.md docs/22_production_release_checklist.md; do
  echo "=== $f ===" && git log -1 --format="%h %ci %s" -- "$f"
done
```

---

## 参照ドキュメント

| ドキュメント | 読むタイミング |
|---|---|
| `CLAUDE.md` (root) | 全開発作業の正本、毎セッション |
| `docs/ops/22_production_release_checklist.md` | production deploy 前 |
| `docs/ops/03_deploy_procedures.md` | Docker / コンテナ操作前 |
| `docs/ops/01_api_endpoints.md` | curl を書く前 |

---

*2026-05-18 / GID 1214891975516570*
