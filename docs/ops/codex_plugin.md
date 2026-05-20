# Codex Plugin 運用ルール (codex-plugin-cc)

> 2026-05-21 refactor で `CLAUDE.md` から分離。

## セットアップ済み
```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
```

## Review Gate: 常時OFF
Review gateは全コード変更で自動レビューが走り、使用量を大量消費する。常時OFFにする。
```
/codex:setup --disable-review-gate
```

## コスト最適化運用ルール
1. **普段の開発** → review gate OFF。Claude Code Agent Teamsで通常開発
2. **PR作成前のみ手動レビュー（1日1-2回）:**
   ```
   /codex:review --base main --background
   /codex:status
   /codex:result
   ```
3. **Aave/セキュリティ変更時のみ adversarial review:**
   ```
   /codex:adversarial-review --base main --background challenge the Aave safety logic and DeFi risk handling
   ```
4. **問題検出時** → Codexの指摘をClaude Codeに貼って修正させる
5. **バグ調査をCodexに委任:**
   ```
   /codex:rescue investigate why the tests started failing
   ```

## やらないこと
- review gate ON（使用量10-20倍になる）
- 小さな変更ごとのレビュー（PR前にまとめて1回）
- Codexだけに頼る（Claude Code + Codex の補完関係）
