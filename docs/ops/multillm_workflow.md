# マルチLLM開発ワークフロー

> 2026-05-21 refactor で `CLAUDE.md` から分離。

## ロール割り当て
| LLM | ロール | 使うタイミング |
|-----|--------|---------------|
| **Claude Opus 4.6** | アーキテクト & インテグレーター | 新モジュール設計、Aave/セキュリティ、統合レビュー |
| **Claude Sonnet 4.5** | 高速実装 (デフォルト) | 実装80%、テスト、バグ修正、ドキュメント |
| **Claude Haiku 4.5** | インフラ & ユーティリティ | Docker、CI/CD、シェルスクリプト |
| **Codex 5.3** | 自動レビュアー | PR作成→GitHub Actions自動実行 |
| **GPT-4o** | クロス判定 (本番のみ) | BUY/SELL判定のPhase B、仕様書共同作成 |

## デバッグ昇格ルール
- フロントエンド / 一般バグ → Sonnet で開始
- 複雑 or 解決しない → Opus に昇格 (`claude --model opus`)
- Aave / セキュリティ → 最初から Opus
- CI / Docker → Haiku (`claude --model haiku`)

## ブランチ戦略
```
feature/* (各LLM担当) → dev (Opus統合) → staging (Codex最終レビュー) → main
```
