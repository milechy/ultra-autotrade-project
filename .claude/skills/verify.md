# /verify — DoD自動検証

## 使い方
コミット前に以下を実行:
```bash
./scripts/verify.sh
```

## チェック項目
1. ruff check（lint）
2. ruff format（フォーマット）
3. mypy（型チェック）
4. pytest + coverage 80%+
5. ruff --select S（セキュリティ）

## ルール
- 全項目PASSしてからコミットすること
- セキュリティチェック（5番）は警告のみ（新規criticalがなければOK）
