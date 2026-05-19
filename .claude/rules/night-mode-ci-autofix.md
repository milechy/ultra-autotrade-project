# Night-Mode CI Auto-Fix Rules

24h 自走中に新規 PR で CI failure が出た場合の自動解消ルール。

---

## 自動解消対象

| 失敗種別 | 対応 |
|---|---|
| `ruff format` / lint I001 等（`--fix` 自動修正可能） | `ruff check . --fix` + `ruff format .` → commit & push |
| ruff Security S-rules（S110 等、文脈で noqa 妥当） | `# noqa: Sxxx` コメント追加 → commit & push |
| `claude-review` FAIL（transient エラー） | GitHub Actions の failed job を re-run のみ |
| `Path Access Control` FAIL（凍結ファイル deps 申請） | `docs/integration/backend_deps.md` にエントリ追加 → commit & push |
| `tsc --noEmit` 軽微な型エラー（型注釈追加で解決） | 型注釈追加 → commit & push |
| pytest 単発 flaky（CI re-run で解消） | failed job を re-run のみ |

---

## 自動解消禁止（除外）

| 失敗種別 | 理由 |
|---|---|
| `E2E Smoke Tests (Playwright)` | staging 実環境依存 → 無視で OK |
| `staging deploy` 系 workflow | 本番影響可能性あり |
| pytest 複数件 fail / coverage 80% 割れ | 本質的問題 → HUMAN-REVIEW-REQUIRED |
| mypy 型エラー大量 | 設計判断が必要 |
| 既存テストが新規 PR で fail | リグレッション → 調査が必要 |

---

## 判断ルール

1. **3往復制限**: 1本の PR で 3往復以上 fix が必要になったら `HUMAN-REVIEW-REQUIRED` に切り替え
2. **PR コメント必須**: 自動 fix 後は以下のコメントを PR に追記
   ```
   🤖 auto-fix by night-mode Lane: [修正内容の1行サマリー]
   ```
3. **翌朝レポートに含める**: 解消できた PR / できなかった PR の一覧を朝レポートに記載

---

## 自動 fix の実施手順

```bash
# 1. ブランチ checkout
git fetch origin <branch> && git checkout <branch>

# 2. ruff 自動修正
cd backend
source .venv/bin/activate
ruff check . --fix
ruff format .

# 3. 確認
ruff check . && ruff format --check .

# 4. commit & push
git add -u
git commit -m "fix(lint): ruff auto-fix (night-mode)"
git push origin <branch>

# 5. PR コメント
gh pr comment <number> --body "🤖 auto-fix by night-mode Lane: ruff format/lint 自動修正"
```

---

## 参照

- CI workflow: `.github/workflows/ci.yml`
- Path Access Control: `.github/workflows/path-check.yml`
- ruff 設定: `backend/ruff.toml` (known-first-party = ["app"] 設定済み)
- 過去適用例: PR #158 (S110 noqa + I001 ruff.toml), PR #181 (backend_deps.md), PR #180-187 (claude-review re-run)
