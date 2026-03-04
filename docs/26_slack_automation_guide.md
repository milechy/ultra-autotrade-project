# 26_slack_automation_guide.md
# Ultra AutoTrade - Slack 自動化ワークフロー運用ガイド

本ドキュメントは、Slack 統合による自動コードレビューワークフローの運用手順をまとめる。

---

## 📋 システム概要

### ワークフロー全体図

```
┌─────────────────┐
│ Claude Code     │  コーディング完了
│ (Codespaces)    │  → git push origin dev/feature-x
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GitHub Actions  │  自動実行
│ (auto-review)   │  1. Codex レビュー実行
└────────┬────────┘  2. review_result.json 生成
         │           3. Slack 通知送信
         ▼
┌─────────────────┐
│ Slack           │  インタラクティブ通知
│ (#dev-review)   │  [✅ Approve] [🔄 Changes] [❌ Reject]
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Slack Handler   │  ボタンクリック処理
│ (Flask API)     │  → GitHub API 呼び出し
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GitHub          │  自動アクション実行
│ (PR management) │  • Approve → PR承認
└─────────────────┘  • Changes → コメント追加
                     • Reject → PR クローズ
```

---

## 🚀 初回セットアップ

### 1. Slack App 作成（30分）

#### 1.1 App 作成
1. https://api.slack.com/apps にアクセス
2. **"Create New App"** → **"From scratch"**
3. App 名: `Ultra AutoTrade Bot`
4. Workspace 選択

#### 1.2 権限設定

**OAuth & Permissions** ページ:
```
Bot Token Scopes:
├── chat:write          # メッセージ送信
├── chat:write.public   # パブリックチャンネル投稿
└── commands            # Slash コマンド（オプション）
```

**Install to Workspace** → Bot Token をコピー（`xoxb-...`）

#### 1.3 Incoming Webhooks

**Incoming Webhooks** ページ:
```
Activate: ON
Add New Webhook to Workspace
  → チャンネル: #ultra-autotrade-dev
  → Webhook URL をコピー
```

#### 1.4 Interactive Components

**Interactivity & Shortcuts** ページ:
```
Interactivity: ON
Request URL: https://77.42.46.155:5000/slack/interactions
  ↑ Slack Handler（Flask API）のURL
```

### 2. GitHub Secrets 設定（5分）

リポジトリの **Settings** → **Secrets and variables** → **Actions**:

```bash
# 必須
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...  # Slack App の Basic Information から
OPENAI_API_KEY=sk-...
GITHUB_TOKEN=ghp_...  # Personal Access Token（repo権限）
```

### 3. Flask API デプロイ（staging サーバー）（30分）

#### 3.1 サーバー準備

```bash
ssh root@77.42.46.155
cd /opt/ultra-autotrade

# Flask 用ディレクトリ作成
mkdir -p slack-handler
cd slack-handler
```

#### 3.2 依存パッケージインストール

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask requests
```

#### 3.3 スクリプト配置

```bash
# slack_handler.py を配置
# （GitHub から git pull または直接コピー）
cp ../scripts/slack_handler.py ./
```

#### 3.4 systemd サービス作成

`/etc/systemd/system/slack-handler.service`:
```ini
[Unit]
Description=Slack Handler for Ultra AutoTrade
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ultra-autotrade/slack-handler
Environment="SLACK_SIGNING_SECRET=xxxxx"
Environment="GITHUB_TOKEN=ghp_xxxxx"
Environment="GITHUB_REPO=yourusername/ultra-autotrade"
Environment="PORT=5000"
ExecStart=/opt/ultra-autotrade/slack-handler/venv/bin/python slack_handler.py
Restart=always

[Install]
WantedBy=multi-user.target
```

#### 3.5 サービス起動

```bash
sudo systemctl daemon-reload
sudo systemctl enable slack-handler
sudo systemctl start slack-handler
sudo systemctl status slack-handler
```

#### 3.6 動作確認

```bash
curl http://localhost:5000/health
# 期待: {"status":"ok"}
```

---

## 🧪 テスト手順

### ローカルテスト（Codespaces）

#### 1. Codex レビューのテスト

```bash
cd /workspaces/ultra-autotrade

# テスト用ダミーファイル作成
echo 'def test(): pass' > test_file.py

# レビュー実行
export OPENAI_API_KEY=sk-...
python scripts/codex_review.py --files test_file.py

# 期待: review_result.json 生成
cat review_result.json
```

#### 2. Slack 通知のテスト

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
python scripts/slack_notify.py --review review_result.json

# Slack チャンネルに通知が届くことを確認
```

---

### E2E テスト（staging）

#### ステップ1: テスト用ブランチ作成

```bash
git checkout -b dev/test-slack-integration

# 簡単な変更を加える
echo '# Test' >> README.md
git add README.md
git commit -m "test: Slack integration test"
git push origin dev/test-slack-integration
```

#### ステップ2: GitHub Actions 確認

1. GitHub リポジトリの **Actions** タブを開く
2. `Automated Code Review` ワークフローが実行中か確認
3. ログを確認:
   ```
   Run Codex review
   Reviewing 1 files...
   ✅ Review complete
   ```

#### ステップ3: Slack 通知確認

1. Slack の #ultra-autotrade-dev チャンネルを確認
2. 以下のようなメッセージが届いているか:
   ```
   🤖 Code Review Complete
   ━━━━━━━━━━━━━━━━━━━━━━
   📁 Files: 1
   ⚠️  Issues: 0
   ✅ Suggestions: 0
   
   [✅ Approve] [🔄 Request Changes] [❌ Reject]
   ```

#### ステップ4: ボタンクリックテスト

1. **[✅ Approve]** をクリック
2. メッセージが更新されることを確認:
   ```
   ✅ PR approved successfully
   ```
3. GitHub で PR がApprove されているか確認

---

## 🛠️ トラブルシューティング

### 問題1: GitHub Actions が実行されない

**症状:**
push してもワークフローが動かない

**確認項目:**
1. ブランチ名が `dev/**` または `feature/**` か
2. `.github/workflows/auto-review.yml` が正しく配置されているか
3. GitHub Actions が有効化されているか（Settings → Actions）

**解決策:**
```bash
# ワークフローファイル確認
cat .github/workflows/auto-review.yml

# 手動トリガー（デバッグ用）
gh workflow run auto-review.yml
```

---

### 問題2: Codex レビューが失敗する

**症状:**
```
ERROR: OpenAI API call failed
```

**確認項目:**
1. `OPENAI_API_KEY` が正しく設定されているか
2. API キーの残高があるか（https://platform.openai.com/account/billing）
3. レート制限に引っかかっていないか（3 RPM）

**解決策:**
```bash
# API キーのテスト
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

---

### 問題3: Slack 通知が届かない

**症状:**
GitHub Actions は成功するが Slack に通知が来ない

**確認項目:**
1. `SLACK_WEBHOOK_URL` が正しいか
2. Webhook の対象チャンネルが正しいか
3. Slack App が有効化されているか

**解決策:**
```bash
# Webhook の手動テスト
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test message"}'
```

---

### 問題4: Slack ボタンが動かない

**症状:**
ボタンをクリックしてもエラーになる

**確認項目:**
1. Flask API（slack_handler.py）が起動しているか
2. Slack App の Request URL が正しいか
3. `SLACK_SIGNING_SECRET` が正しく設定されているか

**解決策:**
```bash
# Flask API の状態確認
sudo systemctl status slack-handler

# ログ確認
sudo journalctl -u slack-handler -f
```

---

## 💰 コスト試算

### OpenAI API（GPT-4）
```
1 レビュー ≈ 2,000 tokens
GPT-4: $0.03/1K input tokens + $0.06/1K output tokens
1 レビュー ≈ $0.06 - $0.12

月間 100 レビュー ≈ $6 - $12
```

### コスト削減オプション
- GPT-3.5-Turbo 使用: 約 1/10 のコスト
- レビュー対象ファイル制限（重要なファイルのみ）
- 手動トリガーのみに限定

---

## 🔐 セキュリティ

### API キー管理
- ✅ GitHub Secrets で管理
- ✅ コードに直接記述しない
- ✅ ログに出力しない
- ✅ 定期的にローテーション

### Slack 通知内容
- ❌ API キー・秘密鍵を含めない
- ❌ フルファイルパスを避ける（相対パスのみ）
- ✅ エラー詳細はログのみ（Slack には要約）

### Flask API
- ✅ Slack 署名検証を有効化
- ✅ HTTPS のみ許可（staging では HTTP も許可）
- ✅ レート制限実装

---

## 📊 運用メトリクス

### 監視項目
| 項目 | 正常値 | アラート条件 |
|------|--------|------------|
| **レビュー成功率** | > 95% | < 90% が 3回連続 |
| **Slack 通知成功率** | 100% | < 100% |
| **平均レビュー時間** | < 30秒 | > 60秒 |
| **OpenAI API コスト** | < $15/月 | > $20/月 |

---

## 🚀 今後の拡張

### Phase 15 候補
- [ ] 自動マージ機能（承認後に自動 merge）
- [ ] レビュー結果の Notion 保存
- [ ] AI による修正提案の自動適用
- [ ] 複数レビュワーの投票システム
- [ ] Slack Thread での議論機能

---

## 📚 参考資料

### Slack API
- https://api.slack.com/docs
- https://api.slack.com/reference/block-kit
- https://api.slack.com/interactive-messages

### GitHub API
- https://docs.github.com/en/rest/pulls
- https://docs.github.com/en/rest/actions

### OpenAI API
- https://platform.openai.com/docs/api-reference
- https://platform.openai.com/docs/guides/code

---

## 📝 変更履歴

| 日付 | 変更内容 | 担当 |
|------|---------|------|
| 2026-02-03 | 初版作成 | Phase 14 |

---

## 付録: スクリプト一覧

### 実装済みファイル
```
scripts/
├── codex_review.py     # Codex レビュー実行
├── slack_notify.py     # Slack 通知送信
└── slack_handler.py    # Slack ボタン処理（Flask API）

.github/workflows/
└── auto-review.yml     # GitHub Actions ワークフロー
```

### 使用方法

#### Codex レビュー
```bash
python scripts/codex_review.py --files "file1.py file2.ts"
python scripts/codex_review.py --diff HEAD~1
```

#### Slack 通知
```bash
python scripts/slack_notify.py --review review_result.json --pr-url https://...
```

#### Flask API 起動
```bash
export SLACK_SIGNING_SECRET=xxxxx
export GITHUB_TOKEN=ghp_xxxxx
python scripts/slack_handler.py
```