# Ultra AutoTrade プロジェクトコンテキスト

## プロジェクト概要
- **目的**: OctoBot x AI x Aave の暗号資産自動運用システム
- **入力**: Notion にニュースURLを貼る
- **出力**: AI判定 -> OctoBot取引 -> Aave資産運用

## アーキテクチャ
- **Backend**: FastAPI (Python 3.11)
- **Frontend**: Next.js (将来実装)
- **State Management**: state.json (fail-closed設計)
- **Network**: Polygon Mumbai (staging), Polygon (production)

## コアな設計原則
1. **Fail-Closed**: エラー時は安全側（停止）に倒す
2. **二重安全機構**:
   - emergency_stop (backend monitoring_service)
   - circuit_closed (nginx circuit breaker)
3. **Single Source of Truth**: state.json がシステム状態の唯一の情報源
4. **Explicit Error Handling**: エラーを隠蔽せず、明確に表面化

## ディレクトリ構造
```
backend/
├── app/
│   ├── aave/          # Aave V3連携（Phase 3完了）
│   ├── automation/    # 監視・緊急停止・レポート
│   ├── bots/          # OctoBot連携
│   ├── ai/            # AI判定ロジック
│   └── notion/        # Notion API連携
├── tests/             # pytest テスト
└── requirements.txt
docs/                  # 設計ドキュメント（真実の情報源）
```

## Phase 進捗
- Phase 1: Notion API連携 (完了)
- Phase 2: AI判定ロジック (完了)
- Phase 3: state.json連携 (完了)
- Phase 4: Web3AaveClient実装 (完了)
- Phase 5: E2E統合テスト (予定)

## 重要なドキュメント
- `docs/07_aave_operation_logic.md`: Aave運用ルール（HF閾値等）
- `docs/08_automation_rules.md`: 監視・アラート・リトライロジック
- `docs/13_security_design.md`: セキュリティ設計（環境変数管理等）
- `docs/14_test_strategy.md`: テスト戦略（ユニット/統合/E2E）

## Best Practices適用状況
- Incremental development: Phaseベースで段階的実装
- Explicit over implicit: 全ての動作を明示的に
- Trust but verify: 全Phase完了後にテスト実施
- Memory persistence: cleanupPeriodDays=99999 で永続化
