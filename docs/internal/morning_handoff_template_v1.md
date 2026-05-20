# 朝引継ぎパッケージ テンプレート v1

> 毎朝 claude.ai セッション開始時に使用。night-mode 完了後の状態を小林さんに伝達し、
> claude.ai が §9 Step 0 を確実に実施できるよう設計。
> Asana タスク GID: 1214961811329677

---

## Step 0: CLI cat テンプレ (dev VPS で実行 / 約3分)

```bash
cd /opt/ultra-autotrade/main

echo "=== CLAUDE.md head 80 ==="
head -80 CLAUDE.md

echo ""
echo "=== 直近 5日の docs 変更 ==="
git log --since="$(date -d '5 days ago' '+%Y-%m-%d')" --oneline -- docs/ | head -20

echo ""
echo "=== 直近 postmortem 5件 ==="
ls -lt docs/postmortems/ 2>/dev/null | head -6

echo ""
echo "=== production 状態 ==="
# 本番 VPS で実行:
# curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
# docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
#   "SELECT action, prompt_version, COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY action, prompt_version;"

echo ""
echo "=== open PR 一覧 ==="
gh pr list --state open --json number,title,headRefName --jq '.[] | "\(.number) \(.headRefName) \(.title)"'
```

---

## 朝レポート枠 (Lane が埋める)

### 1. Night-mode 完了タスク

| GID | タスク名 | 結果 | PR |
|---|---|---|---|
| (GID) | (タスク名) | ✅完了 / ⚠️部分 / ❌失敗 | #(番号) |

### 2. Merge 済み PR

- #(番号): (タイトル)

### 3. HUMAN-REVIEW 停止タスク

| GID | タスク名 | 停止理由 |
|---|---|---|
| (GID) | (タスク名) | 本番 deploy 必要 / Tier S / その他 |

### 4. 本番状態スナップショット

```
scheduler_healthy: true/false
prompt_version (最新): v4/v3/v1
ai_decisions 直近 24h: BUY N件 / SELL N件 / HOLD N件
staging alive: yes/no
proposals pending: N件
```

### 5. PR CI 状態

| PR# | タイトル | CI | 推奨アクション |
|---|---|---|---|
| #(番号) | (タイトル) | ✅pass / ❌fail | merge OK / 要修正 |

---

## userMemory 追加候補枠

前日の §25 違反新規パターン:
```
(内容があれば記載、なければ「特記なし」)
```

追加先: claude.ai プロジェクト「プロジェクトの手順」> userMemories セクション
担当: 小林さん (手動)

---

## 本日最優先

### Tier S (1本、Opus 4.7)
- タスク: (名前) / GID: (GID)
- 着手時刻: (時刻)

### Tier A (1-2本)
- (名前) / GID: (GID)

### Tier B 並列 (Agent View)
```bash
claude --bg "(Lane プロンプト1)"
claude --bg "(Lane プロンプト2)"
claude agents  # 状態確認
```

---

## 最初の Lane 指示プロンプト枠

```
【朝プロトコル Lane】
Step 0 実施: CLAUDE.md head 80 + production_operation_checklist.md を cat して結果を返す
実機確認:
  - curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
  - ai_decisions 直近 24h 件数 (action 別)
  - staging alive (docker ps | grep staging-new | wc -l)
  - open PR CI 状態 (gh pr list --state open)
報告形式: 1ブロックで全結果をまとめて返す
制約: 本番 deploy は HUMAN-REVIEW-REQUIRED で停止
```

---

*v1 作成: 2026-05-20 / Claude Code*
*次回更新: night-mode 運用で得た教訓を v2 に反映*
