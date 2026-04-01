# Development Workflow

## 開発体制 v2（2026-03-20〜）
- claude.ai: PM/アーキテクト/Asana管理
- Claude Code Agent Teams: 並行開発の主力（tmux + iTerm2、3-5 peers）
- Slack #ultra-auto-project: 完了通知・CI・承認リクエスト
- Asana: タスク管理（プロジェクトGID: 1213741124336104）

## マルチLLM ロール割り当て
| LLM | ロール | 使うタイミング |
|-----|--------|---------------|
| Claude Opus 4.6 | アーキテクト & インテグレーター | Aave/セキュリティ、統合レビュー |
| Claude Sonnet 4.6 | 高速実装 (デフォルト) | 実装80%、テスト、バグ修正 |
| Claude Haiku 4.5 | インフラ & ユーティリティ | Docker、CI/CD、シェルスクリプト |
| GPT-4o | クロス判定 (本番のみ) | BUY/SELL判定のPhase B |

## デバッグ昇格ルール
- フロントエンド / 一般バグ → Sonnet で開始
- 複雑 or 解決しない → Opus に昇格
- Aave / セキュリティ → 最初から Opus
- CI / Docker → Haiku

## ブランチ戦略
feature/* → dev (統合) → staging (レビュー) → main

## Testing
- Unit: pytest + mypy strict + ruff
- LLM: VCR replay (record once, replay in CI)
- E2E: Playwright (mobile viewport)
- Aave: Sepolia testnet before mainnet
- Exchange: bitFlyer sandbox
- Coverage gate: 80%+

## 開発原則
1. Start Small, Iterate — 大きな機能は小さく分割
2. Explicit is Better than Implicit — 暗黙の副作用を避ける
3. Trust but Verify — コード生成後は必ずテスト実行
4. Use Plan Mode for High-Risk Changes — Aave/State関連は必ずPlanモード
