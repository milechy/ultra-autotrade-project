# Pre-Commit Diff Review

## ルール
コミット前に必ず以下を実行:

1. `git diff --cached` で差分を確認
2. 意図しない変更が含まれていないか目視チェック
3. .env, secrets, API keys が含まれていないか確認
4. 変更が1つの論理的な単位にまとまっているか確認

## 自動チェック
`scripts/verify.sh` を実行して全DoDを通過させてからコミットする。
