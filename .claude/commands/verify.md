# verify — Definition of Done チェック

このプロジェクトの完了条件（DoD）を一括チェックします。

## 実行手順

1. ruff lint チェック:
   ```bash
   cd backend && ruff check .
   ```

2. ruff format チェック:
   ```bash
   cd backend && ruff format --check .
   ```

3. mypy strict チェック:
   ```bash
   cd backend && mypy app/ --config-file ../pyproject.toml
   ```

4. pytest + coverage 80%:
   ```bash
   cd backend && python -m pytest tests/ --cov=app --cov-fail-under=80 -q
   ```

5. セキュリティチェック（hardcoded secrets）:
   ```bash
   cd backend && ruff check . --select S
   ```

全ステップが通過したら「✅ DoD PASS」と報告。
1つでも失敗したら、失敗箇所と修正方針を報告。
