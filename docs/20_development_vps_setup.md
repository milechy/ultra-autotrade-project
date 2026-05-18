# 20_development_vps_setup.md
# 開発VPS構築ガイド (2026-05-18 初版)

> 2026-05-18 に **開発専用 VPS** を追加し、dev / staging / production の 3 層運用へ移行した。
> 本ドキュメントは開発 VPS（`uata-dev-01` / `77.42.79.75`）の仕様・認証・運用ポリシーを
> 司令塔(claude.ai) userMemories #5/#28/#29/#30 と整合する形でまとめる。
> 本番 / staging 環境設定は `docs/21_production_environment_config.md` /
> `docs/17_staging_environment_config.md`、混同防止は `docs/21` §0 を参照。
>
> ※ docs/20 番は `20_phased_capital_injection.md` / `20_staging_release_checklist.md`
> が既存。本ファイルは 3 つ目の 20 番（指示により命名）。

---

## 1. 仕様

| 項目 | 値 |
|------|----|
| IP | `77.42.79.75` |
| ssh alias | `uata-dev`（**Mac** `~/.ssh/config` に定義。VPS 側 `~/.ssh/config` には未定義） |
| Provider | Hetzner CPX32 Helsinki (eu-central) |
| OS | Ubuntu 24.04 LTS（実測 24.04.4 LTS）, kernel 6.8.0（実測 6.8.0-90-generic） |
| CPU / RAM / Disk | 4 vCPU AMD / 8 GB / 160 GB SSD |
| Swap | 2 GB swapfile（`/swapfile`） — ※状態は §5 参照 |
| Timezone | JST (Asia/Tokyo) |
| User | `uata`（NOPASSWD sudo, docker group） |

---

## 2. 認証

| 用途 | 鍵 / アカウント | 備考 |
|------|-----------------|------|
| SSH ログイン | `~/.ssh/hetzner_uata_dev` | Hetzner Console 登録名: `uata-dev@kobayashihirokinoiMac` |
| GitHub Deploy key | `~/.ssh/uata_github_deploy` | `milechy/ultra-autotrade-project`（Read/Write 許可）。SSH config alias: `github-uata` |
| Claude Code Max | `sic.nozawa@gmail.com` | Mac / VPS 両環境で同一アカウント |
| Claude Code config | `CLAUDE_CONFIG_DIR=~/.claude-uata` 方式 | アカウント切替方式 |

- リモート: `git@github-uata:milechy/ultra-autotrade-project.git`（SSH / deploy key 経由）
- 本番 VPS への SSH（`ultra@77.42.46.155`）は本 VPS の用途外。混同防止は §3 / `docs/21` §0。

---

## 3. 3 層運用ポリシー

| 層 | ホスト | 役割 |
|----|--------|------|
| **dev**（本 VPS） | `77.42.79.75` | コード編集 + pytest + `npm dev` + `verify.sh`、ある程度の動作確認まで |
| **staging** | 本番 VPS `*-staging-new` コンテナ | Base Sepolia + Shadow Mode |
| **production** | 本番 VPS `*-production` コンテナ | 実資金 Base Mainnet |

- **本番 Secret は絶対に開発 VPS に置かない**
- API キーは**ダミーまたは Sandbox / Testnet のみ**
- 正規フロー: dev で実装 → PR → ローカル Mac で merge → GitHub push →
  本番 Hetzner `git pull origin main` → `deploy_production.sh`（本番 VPS は pull only）

---

## 4. ディレクトリ構造

```
/opt/
├── ultra-autotrade/
│   └── main/                       # メイン worktree（default branch）
└── ultra-autotrade-worktrees/
    └── <branch>/                   # 並列開発 worktree（Tier B レーン物理分離）
```

- 全 worktree とブランチ・SHA: `git worktree list`
- 各レーンは自分の worktree で完結。**他 worktree のファイルは編集しない**（コンフリクト回避）
- ツリー詳細は `docs/03_directory_structure.md` §開発VPS構成 を参照

---

## 5. Phase 6 構築済みコンポーネント (2026-05-18)

> 別 Claude Code セッションが `/opt/ultra-autotrade/main` で Phase 6 環境構築を並行実行中。
> 下表「ライブ計測」は本ドキュメント commit 時点（2026-05-18）の実測値（推測なし）。

| コンポーネント | 仕様（目標構成） | ライブ計測（commit 時点） |
|----------------|------------------|---------------------------|
| `backend/.venv` | Python 3.12 venv | ✅ 構築済み（`python --version` → **Python 3.12.3**） |
| `frontend/node_modules` | `npm install --legacy-peer-deps` 済 | ✅ 構築済み |
| `.env.local` | `.env.local.example` からダミー値で配置 | ✅ 配置済み（518 B） |
| swap | 2 GB enabled（`/swapfile`） | ⏳ **未反映**（`swapon --show` 空 / `free -h` Swap 0B / `/swapfile` 不在） |

> ⚠️ **swap の仕様と実測の乖離**: Phase 6 仕様では 2 GB `/swapfile` を有効化するが、
> 本 doc commit 時点のライブ計測では未反映。並行 Phase 6 セッションが swap ステップを
> 未適用のため。完了確認まで「Phase 6 完了」と断定しない（CLAUDE.md §開発環境 v3 準拠 /
> メモリ #20 仮説と明記）。確認コマンド: `swapon --show` / `free -h | grep -i swap`。

### 構築コマンド（参考 / Phase 6 セッションが実行）

```bash
# venv (Python 3.12)
cd /opt/ultra-autotrade/main/backend && python3.12 -m venv .venv
. .venv/bin/activate && pip install -r requirements.txt

# frontend
cd /opt/ultra-autotrade/main/frontend && npm install --legacy-peer-deps

# swap 2GB（VPS 設定変更を伴うため Phase 6 セッション側で実施。本 doc は手順記載のみ）
#   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
#   sudo mkswap /swapfile && sudo swapon /swapfile
#   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# .env.local
cp /opt/ultra-autotrade/main/.env.local.example /opt/ultra-autotrade/main/.env.local
```

---

## 6. 監査文書

| ファイル | 内容 |
|----------|------|
| `~/Desktop/uata_dev_vps_setup_audit.md` | 初回監査 |
| `~/Desktop/uata_dev_vps_setup_audit_followup.md` | 4 件解消フォローアップ |

（上記は開発者 Mac / VPS の Desktop に配置。リポには含めない。）

---

## 7. 司令塔 (claude.ai) との整合

| 整合先 | 内容 |
|--------|------|
| userMemories #5 | Hetzner VPS 2 拠点運用 |
| userMemories #28 | 3 層環境運用（dev / staging / production） |
| userMemories #29 | 開発 VPS 監査結果 |
| userMemories #30 | `docs/ops/05` 鮮度問題（→ `docs/ops/05` §2026-05-18 監査注釈で対応） |
| Project Files | `production_operation_checklist.md` ゲート0 セクション（混同防止） |
| Custom Instructions | 開発環境 v3 (2026-05-18〜)（→ CLAUDE.md §開発環境 v3 と整合） |

- 本 VPS 関連の運用ルールは CLAUDE.md §開発環境 v3 / §並列開発フロー v4 を参照
- 本番 / staging への操作は本ドキュメントの対象外（`docs/21` / `docs/17` / `docs/ops/03`）
