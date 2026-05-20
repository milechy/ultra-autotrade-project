# Codex Plugin 運用ルール (codex-plugin-cc) — **未採用 / 参考のみ**

> ⚠️ **本リポジトリでは Codex Plugin を採用していない。** Gate 6 のコードレビューは
> Claude Code 公式 slash command **`/review`** (および `/security-review`) を使用する。
>
> 本ファイルは 2026-05-21 refactor (`CLAUDE.md` 分割) 時に旧記述を保全したアーカイブ。
> 採用判断が変わった場合の参考として残置。新規 Lane では `/review` を使用すること。

## 現行 (採用中) のレビュー手段

```
/review            # PR レビュー (本リポジトリでの Gate 6 公式ルート)
/review <PR番号>   # PR 番号を明示
/security-review   # 現在ブランチの pending changes 用セキュリティレビュー
```

GitHub Actions 側にも `Codex 5.3 Auto Review` workflow が並走するが、それは
plugin ではなく GHA 経由の自動レビュー。本セクションの「Codex Plugin (CLI plugin)」とは別物。

---

## 参考: 旧記述 (Codex Plugin を採用する場合の手順)

> 以下は「もし Codex Plugin を採用するなら」の参考。**現状本 repo では未使用**。

### セットアップ手順 (未実施)

```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
```

### Review Gate: 常時OFF

Review gate は全コード変更で自動レビューが走り、使用量を大量消費する。
採用する場合は常時 OFF が前提:

```
/codex:setup --disable-review-gate
```

### コスト最適化運用 (採用時想定ルール)

1. **普段の開発** → review gate OFF。Claude Code Agent Teams で通常開発
2. **PR 作成前のみ手動レビュー（1日1-2回）:**
   ```
   /codex:review --base main --background
   /codex:status
   /codex:result
   ```
3. **Aave / セキュリティ変更時のみ adversarial review:**
   ```
   /codex:adversarial-review --base main --background challenge the Aave safety logic and DeFi risk handling
   ```
4. **問題検出時** → Codex の指摘を Claude Code に貼って修正させる
5. **バグ調査を Codex に委任:**
   ```
   /codex:rescue investigate why the tests started failing
   ```

### やらないこと (採用時)

- review gate ON（使用量10-20倍になる）
- 小さな変更ごとのレビュー（PR前にまとめて1回）
- Codex だけに頼る（Claude Code + Codex の補完関係）
