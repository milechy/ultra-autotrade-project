# Ultra AutoTrade — Claude Code ガイド

## [CRITICAL] Security Rules
1. Private keys: environment variables ONLY. Never hardcode. Never log.
2. Health Factor < 1.6 → automatic HARD_STOP
3. Max single trade: 10% of total assets
4. Max daily trades: 30% of total assets
5. Cooldown: 10 minutes between Aave operations
6. Emergency stop flag: OR logic — manual stop can NEVER be overwritten
7. .env.staging and .env.production MUST use physically different keys
8. No tokens/keys in logs — mask to first 6 + last 4 chars
9. main branch: no direct push, PR + review required
10. LLM output MUST be JSON Schema validated — parse failure → HOLD
11. Financial calculations: Decimal type ONLY (never float)

## [CRITICAL] Definition of Done (DoD)
コミット前に以下を全通過:
1. `ruff check .` — lint エラー 0
2. `ruff format --check .` — フォーマット違反 0
3. `mypy app/ --config-file ../pyproject.toml` — 型エラー 0
4. `pytest tests/ --cov=app --cov-fail-under=80 -q` — 全通過 + coverage 80%+
5. `ruff check . --select S` — セキュリティ警告確認

## Core Principles
1. **Simplicity First** — 最小限の変更で目的を達成。過剰な抽象化不要
2. **No Laziness** — テスト・lint・フォーマットを省略しない
3. **Minimal Impact** — 既存コードへの影響を最小化

## Frontend ルール
- package.json変更時は `npm install --legacy-peer-deps` → package-lock.json も一緒にコミット
- rechartsは必ず `dynamic(() => import('./XxxRecharts'), { ssr: false })` で読み込む（SSRクラッシュ防止）
- `grep -E "ignoreBuildErrors|ignoreDuringBuilds" frontend/next.config.js` でOOMワークアラウンド確認

## Agent Teams Slack通知（必須）
タスク完了時:
```bash
WEBHOOK=$(grep SLACK_WEBHOOK_URL .env.staging | cut -d= -f2-)
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text": "✅ [チームメイト名] 完了: [タスク名]\n結果: [1行サマリー]\nファイル: [変更したファイル一覧]"}'
```

エラー時:
```bash
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text": "❌ [チームメイト名] エラー: [タスク名]\n原因: [エラー内容]"}'
```

---

## 参照ファイル（必要な時だけ読む）

| ファイル | 内容 | いつ読むか |
|---------|------|----------|
| rules/architecture.md | スタック、API一覧、ディレクトリ構造、実行順序 | 新モジュール作成時、API追加時 |
| rules/workflow.md | 開発体制、LLMロール、ブランチ戦略、テスト戦略、開発原則 | Phase開始時、デバッグ昇格判断時 |
| lessons.md | ミスパターン蓄積（3回でDoD昇格） | 同種のエラー発生時 |
| AGENT_TEAMS_DEV_FLOW.md | Agent Teams並行開発フロー、チェックリスト | Phase開始時 |
| docs/13_security_design.md | セキュリティ設計詳細 | Aave/認証関連の実装時 |
| docs/14_test_strategy.md | テスト戦略詳細 | テスト設計時 |
| docs/28_staging_cors_csp_postmortem.md | CORS/CSPインシデント対策 | CORS/CSP問題発生時 |
| docs/29_tunnel_ops_guide.md | Cloudflare Tunnel運用手順 | Tunnel再起動時 |
| deploy_staging.md | Stagingデプロイ手順 | デプロイ時 |
| tester_onboarding_runbook.md | テスター環境構築 | テスターオンボーディング時 |
| docs/34_phase2_protocols_guide.md | Phase 2 マルチプロトコル技術ガイド | Lido/Pendle/Optimizer/Risk Engine実装時 |

---

## Current Phase: Phase 2 コア実装完了（feature/phase2-protocols）

- Phase 2コア実装完了: Lido PoC / Pendle PoC / AI Optimizer（ENB）/ Risk Engine
- BaseProtocolClient インターフェース（OCP準拠）導入済み
- Optimizer ↔ Risk Engine 統合済み（動的リスクスコア取得）
- フロントエンド: 戦略選択画面（/user/strategies）+ プロトコルヘルスモニター（/admin/protocols）
- テスト: 1754 passed（feature/phase2-protocols ブランチ）
- 残り: テスター運用完了確認 → dev マージ → staging デプロイ → E2Eテスト
