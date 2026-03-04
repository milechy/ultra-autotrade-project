# Slack 自動化ワークフロー - クイックスタートガイド

**目標時間: 2時間**

---

## ✅ チェックリスト

### Phase 1: Slack App セットアップ（30分）
- [ ] Slack App 作成
- [ ] Bot Token 取得
- [ ] Webhook URL 取得
- [ ] Interactive Components 設定
- [ ] GitHub Secrets 登録

### Phase 2: スクリプト配置（15分）
- [ ] `scripts/codex_review.py` をリポジトリに追加
- [ ] `scripts/slack_notify.py` をリポジトリに追加
- [ ] `scripts/slack_handler.py` を staging サーバーに配置

### Phase 3: GitHub Actions 設定（15分）
- [ ] `.github/workflows/auto-review.yml` を追加
- [ ] main ブランチにマージ

### Phase 4: Flask API デプロイ（30分）
- [ ] staging サーバーに Flask 環境構築
- [ ] systemd サービス作成
- [ ] サービス起動確認

### Phase 5: テスト（30分）
- [ ] ローカルテスト（Codespaces）
- [ ] E2E テスト（staging）
- [ ] Slack 通知確認
- [ ] ボタンクリック確認

---

## 🚀 最短コマンド集

### 1. GitHub Secrets 登録（ワンライナー）

```bash
# GitHub CLI を使用
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/..."
gh secret set SLACK_BOT_TOKEN --body "xoxb-..."
gh secret set OPENAI_API_KEY --body "sk-..."
gh secret set SLACK_SIGNING_SECRET --body "..."
gh secret set GITHUB_TOKEN --body "ghp_..."
```

### 2. スクリプト配置（ワンライナー）

```bash
# Codespaces で実行
cd /workspaces/ultra-autotrade
mkdir -p scripts .github/workflows
# 各ファイルを配置（Claude.ai からダウンロード）
git add scripts/ .github/workflows/
git commit -m "feat: Add Slack automation workflow"
git push origin main
```

### 3. Flask API デプロイ（ワンライナー）

```bash
# staging サーバーで実行
ssh root@77.42.46.155 'cd /opt/ultra-autotrade && \
  git pull && \
  mkdir -p slack-handler && \
  cd slack-handler && \
  python3 -m venv venv && \
  source venv/bin/activate && \
  pip install flask requests'
```

---

## 🧪 即座にテスト

### テスト用ダミーコミット

```bash
git checkout -b dev/test-slack
echo '# Test' >> README.md
git add README.md
git commit -m "test: Slack automation"
git push origin dev/test-slack
```

→ 数分後に Slack に通知が来る！

---

## 📞 サポート

問題が発生した場合:
1. `docs/26_slack_automation_guide.md` のトラブルシューティングを確認
2. GitHub Actions のログを確認
3. Slack Handler のログを確認（`sudo journalctl -u slack-handler -f`）

---

## 🎉 成功の確認

以下がすべて動作すれば完了:
- ✅ dev/** ブランチへの push で GitHub Actions が実行される
- ✅ Slack に通知が届く
- ✅ ボタンをクリックすると PR がApprove/Reject される
- ✅ GitHub PR に自動コメントが付く