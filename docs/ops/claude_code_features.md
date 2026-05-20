# Claude Code 最新機能活用ガイド（2026年4月 v2.1.89〜v2.1.92）

> 2026-05-21 refactor で `CLAUDE.md` から分離。

## 1. カスタムサブエージェント + @メンション呼び出し

`.claude/agents/` にMarkdownファイル（YAMLフロントマター付き）でサブエージェントを定義。
プロンプト内で `@agent-name` と入力するだけで呼び出し可能（v2.1.89〜のTypeahead対応）。
プロジェクトにコミットすればチーム共有される。

**Ultra AutoTrade 定義済みエージェント（`.claude/agents/`）:**

| ファイル | 役割 | 呼び出し例 |
|---------|------|-----------|
| `security-reviewer.md` | Aave/DeFiセキュリティレビュー | `@security-reviewer backend/app/aave/client.pyをレビューして` |
| `test-runner.md` | 7段階DoDゲート一括実行 | `@test-runner verify.shを実行して結果を報告して` |
| `i18n-checker.md` | 多言語対応チェック | `@i18n-checker frontend/の翻訳漏れをチェックして` |
| `deploy-checker.md` | デプロイ前チェックリスト実行 | `@deploy-checker stagingデプロイ前チェックを実行して` |

## 2. Named Subagents → Agent Teams 連携

`.claude/agents/` で定義したサブエージェントをAgent Teamsのチームメイトとしてそのまま利用可能。
```
spawn a teammate using the security-reviewer agent type to audit the aave module
```
- `tools` 制限とsystem promptは引き継がれる
- `skills` と `mcpServers` フロントマターはTeammate時には適用されない（通常セッション設定を使用）
- Agent Teams運用ルール（Slack通知等）は `CLAUDE.md` の「Agent Teams 運用ルール」セクションに従うこと

## 3. PreToolUse Hooks の `defer` パーミッション（v2.1.89）

ヘッドレスセッション（`-p` モード）でツール呼び出しを一時停止し、後から `--resume` で再評価できる。

**Ultra活用:** FTパイプライン（`~/ft-automation/`）の `claude --print` 実行で、Aave関連ファイル変更等の重要操作のみ承認フローを挟む。

## 4. PermissionDenied フック（v2.1.89）

autoモードの分類器がツール実行を拒否した後に発火するフック。`{retry: true}` を返せば再試行。
Agent Teams自動実行時のフォールバック制御に有用。

## 5. MCP結果サイズ上限 500K文字（v2.1.91）

`_meta["anthropic/maxResultSizeChars"]` で50万文字まで拡大。
Asana MCP（プロジェクトGID: 1213741124336104 等）やSlack MCP（#ultra-auto-project: C0ACS09FMGC）から大量データ取得時に結果切れ問題を軽減。

## 6. `/cost` モデル別・キャッシュヒット内訳（v2.1.92）

Agent Teams使用時のモデル別トークン消費を可視化。Opus/Sonnet/Haiku のコスト配分を確認。
```
/cost
```

## 7. Write tool 差分計算 60%高速化（v2.1.92）

大きなファイル（タブや特殊文字含む）の書き込みが高速化。
workflow.py、scheduled_tasks.py 等の大ファイル編集で体感改善。

## 8. MCP_CONNECTION_NONBLOCKING=true（v2.1.89）

`-p` モードでMCP接続待ちをスキップ。MCPサーバー接続は5秒上限にバウンド。
**Ultra活用:** FTパイプラインの `claude --print --dangerously-skip-permissions` 実行の高速化。

## 9. --exclude-dynamic-system-prompt-sections（printモード）

ユーザー間でプロンプトキャッシュを共有しやすくする。FTパイプライン等のバッチ実行のコスト削減。
```bash
claude --print --exclude-dynamic-system-prompt-sections "タスク内容"
```

## 10. /powerup — インタラクティブ学習（v2.1.90）

Claude Codeの機能をアニメーションデモで学べるコマンド。新機能のキャッチアップに。
```
/powerup
```

## 11. CLAUDE_CODE_NO_FLICKER=1（v2.1.89）

alt-screen描画でフリッカーを抑制。長時間セッション・Agent Teams運用時（tmux + iTerm2）のターミナル表示安定化。

## 12. Monitor tool — バックグラウンドスクリプト監視（v2.1.91）

バックグラウンドで実行中のスクリプトからイベントをストリーム受信。
デプロイ中の `docker compose logs -f` やpytestの長時間実行をモニタリングしながら並行作業可能。

## 13. --resume セッション再開の改善（v2.1.92）

deferred tools、MCPサーバー（Asana/Slack）、カスタムエージェント使用時の `--resume` がプロンプトキャッシュミスを起こす問題が修正。長時間作業の中断・再開がスムーズに。

## 推奨 settings.json 追加設定

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    "CLAUDE_CODE_NO_FLICKER": "1",
    "MCP_CONNECTION_NONBLOCKING": "true"
  }
}
```

**注意:** 上記は `~/.claude/settings.json` またはプロジェクトの `.claude/settings.json` に追加。
既存の `cleanupPeriodDays: 99999` 設定と共存可能。
