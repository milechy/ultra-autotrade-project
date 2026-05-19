# UATa 24h 自走起動前チェックリスト

> 確立: 2026-05-19（24h 自走起動準備フェーズの教訓から）
> 目的: Bypass Permissions 不発・secrets 未配置・session 再起動による進捗喪失を起動前に潰す。

24h 自走（Claude Code CLI）を起動する**前に**、以下 8 項目を順に確認する。
1 項目でも未充足なら起動しない。

## チェックリスト（8 項目）

1. **Bypass Permissions が settings.json に正しくネストされている**
   `permissions.defaultMode = "bypassPermissions"`（root 直下は無効）。
   または起動を `claude --dangerously-skip-permissions` で行う（公式推奨の確実な方法）。
   確認: `python3 -c "import json,sys;d=json.load(open('.claude/settings.json'));print(d.get('permissions',{}).get('defaultMode'))"`

2. **GitHub PAT が env に読み込まれている**
   `~/.claude-uata/secrets/github.env` に `GH_TOKEN`（scope: `repo`, `workflow`）。
   確認: `set -a; source ~/.claude-uata/secrets/github.env; set +a; gh auth status`

3. **Slack webhook が配置・到達可能**
   `~/.claude-uata/secrets/slack.env` に `SLACK_WEBHOOK_URL`（#ultra-auto-project）。
   確認: `grep -q SLACK_WEBHOOK_URL ~/.claude-uata/secrets/slack.env && echo OK`

4. **Pushover が配置・到達可能**
   `~/.claude-uata/secrets/pushover.env` に `PUSHOVER_APP_TOKEN` / `PUSHOVER_USER_KEY`、
   `scripts/uata-pushover-notify.sh` が存在し実行可能（mode 600 の secrets を source）。
   確認: `bash scripts/uata-pushover-notify.sh test`（Normal + High が届く）

5. **stuck-detector が起動済み**
   `./scripts/uata-stuck-detector.sh start` 実行済、`ps aux | grep stuck-detector` で PID 確認。
   起動直後の誤発火防止に `touch /tmp/uata-heartbeat` でリセット。

6. **正本確認（鉄則8）完了**
   CLAUDE.md「並列開発フロー v4 鉄則8」の朝プロトコル正本確認テンプレートを CLI で流し、
   結果をセッションに貼付済（claude.ai プロジェクトファイルは古い前提）。

7. **安全境界がセッション冒頭に明示されている**
   本番 deploy 禁止 / DB migration・.env・secrets・金融閾値・法務 = HUMAN-REVIEW-REQUIRED で停止 /
   並列 tool call 最大 2 本 / HUMAN-REVIEW-REQUIRED は Pushover High。

8. **タスク計画と auto-memory への記録方針が確定**
   Phase 分解・DoD・Asana 連携先を起動前に決め、進捗は逐次 auto-memory に書く
   （session 再起動で auto-memory 未記録の進捗は失われるため）。

## 関連教訓

- Bypass Permissions / dev VPS secrets / session 再起動リスク の詳細は
  CLAUDE.md「## 2026-05-19追加（24h 自走起動準備の教訓）」を参照。
- 並列 tool call 最大 2 本の根拠は CLAUDE.md「### 並列 tool call は最大 2 本まで」を参照。
