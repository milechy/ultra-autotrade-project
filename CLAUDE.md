# Claude Code 開発ガイド

## プロジェクト: Ultra AutoTrade

Based on:
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)

---

## Claude Code 設定

### グローバル設定
**ファイル**: `~/.claude/settings.json`
```json
{
  "cleanupPeriodDays": 99999
}
```
- **効果**: メモリ永続化（プロジェクトコンテキスト長期保持）
- **デフォルト**: 30日（短すぎる）

---

## 開発原則

### 1. Start Small, Iterate
- 大きな機能は小さく分割
- 例: Web3AaveClient
  1. まず `get_health_factor()` のみ
  2. 次に `deposit()` + テスト
  3. 最後に `withdraw()` + 統合テスト

### 2. Explicit is Better than Implicit
- 全ての動作を明示的に
- 暗黙の副作用を避ける
- ログには「何をしたか」「なぜしたか」を記録

### 3. Trust but Verify
- コード生成後は必ずテスト実行
- staging環境で動作確認
- ログとトランザクションを確認

### 4. Use Plan Mode for High-Risk Changes
- Aave / Automation / State 関連は必ず Plan モード
- 変更内容をレビューしてから実行

---

## プロジェクト固有の重要原則

### Fail-Closed Design
- エラー時は安全側（停止）に倒す
- state.json パースエラー -> `emergency_stop=True`
- RPC接続エラー -> NOOP返却

### 二重安全機構
- **Backend**: `emergency_stop` (monitoring_service)
- **Infrastructure**: `circuit_closed` (nginx)
- どちらか一方が有効なら動作抑止

### Code Preference: Explicit Error Handling
```python
# Bad: Silent failure
try:
    risky_operation()
except:
    pass

# Good: Explicit propagation
try:
    risky_operation()
except SpecificError as exc:
    logger.error("Operation failed: %s", exc)
    raise SafetyError(f"Cannot proceed: {exc}") from exc
```

---

## テスト戦略

### ユニットテスト
- 外部依存はモック（Web3, Notion API等）
- 既存テストを壊さない
- 新機能には必ずテスト追加

### 統合テスト
- `@pytest.mark.integration` を使用
- テストネット（Mumbai）で実施
- 少額（< 10 USD相当）でテスト

### E2Eテスト
- staging環境でのみ実施
- Notion -> AI -> OctoBot -> Aave の全フロー

---

## 禁止事項

- `.env.staging` のコミット
- 本番ウォレットの使用
- `emergency_stop` の無効化
- エラーをsilentに握りつぶすコード
- 500行を超える単一ファイル（分割推奨）

---

## 参照ドキュメント

### 設計ドキュメント（Single Source of Truth）
- `docs/07_aave_operation_logic.md`: Aave運用ルール
- `docs/08_automation_rules.md`: 監視・アラート
- `docs/13_security_design.md`: セキュリティ設計
- `docs/14_test_strategy.md`: テスト戦略

### Skills
- `ultra-autotrade-context`: プロジェクト全体像
- `aave-development`: Aave実装ガイド
- `state-management`: state.json管理

---

## Phase 進捗

## 現在の状態（Phase 12 完了）

**完了した主要機能:**
- ✅ Notion → AI → OctoBot → Notion 自動ワークフロー（5分ごと自動実行）
- ✅ Frontend dashboard（日本語化完了）
- ✅ Partner testing environment（staging: 77.42.46.155）
- ✅ 認証システム（SQLite-based）
- ✅ 193+ passing tests
- ✅ 25+ ドキュメント

**環境:**
- Development: Codespaces
- Staging: 77.42.46.155 (testnet)
  - Frontend: http://77.42.46.155:3000
  - Backend: http://77.42.46.155:8000
- Production: 未デプロイ

**Tech Stack:**
- Backend: FastAPI (Python 3.11+)
- Frontend: Next.js + Mantine UI（日本語化済み）
- Database: Notion, SQLite
- Infrastructure: Docker Compose, Hetzner Cloud
```

---

### Step 4: 保存 & 再起動

1. **Ctrl+S / Cmd+S** で保存
2. **Cmd+Shift+P → "Developer: Reload Window"**

---

### Step 5: 動作確認

Claude Code で新しい会話:
```
Ultra AutoTrade プロジェクトの現在のフェーズは？
```

**期待される回答:**
```
Phase 12 が完了しています。主な成果:
- Notion → AI → OctoBot 自動ワークフロー
- UI 日本語化
- Partner testing 環境（staging）
- 193+ テスト

---

## Tips

### Plan モードの活用
```
User: "Web3AaveClient を実装して"

期待される動作:
1. Skills読み込み（aave-development）
2. 実行計画表示（変更ファイル・差分）
3. ユーザー承認待ち
4. 承認後に実行
```

### Incremental Development
- 1コミットあたり5ファイル以下
- 1ファイルあたり500行以下（警告）
- PRはできるだけ小さく

### Error Handling
- 過度なtry-exceptは避ける
- エラーは明確に伝播させる
- ログには詳細を残す

### Memory Persistence
- `~/.claude/settings.json` で永続化済み
- プロジェクトコンテキストを長期保持
- 再起動してもコンテキスト維持

---

## クイックコマンド

```bash
# テスト実行
python -m pytest backend/tests/ -v

# Aave関連テストのみ
python -m pytest backend/tests/test_aave*.py -v

# カバレッジ
python -m pytest backend/tests/ --cov=backend/app --cov-report=html

# 型チェック（mypy）
mypy backend/app/

# フォーマット（black）
black backend/
```
