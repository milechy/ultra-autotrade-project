# Fee Model v10 (F-1〜F-16 進行中、2026-04-25〜)

> 2026-05-21 refactor で `CLAUDE.md` から分離。
> 詳細は `docs/45_fee_model_v10_migration_plan.md` 参照。F-2/F-3 で確定したルール:

## Tier (投資ティア、F-2)
- 内部値: `LOWER` / `MIDDLE` / `UPPER` (v10 三層、JPY 境界 100 万 / 1000 万)
- v9 互換値 `GENERAL` は deprecated として残置 (F-13 で削除)
- 日本語ラベル辞書: `app.auth.models.TIER_JP_LABELS`
- 判定関数: `app.users.tier_service.determine_tier_jpy(deposit_jpy)`
- 既存 6 ユーザーの再判定 SQL: `docs/46_users_tier_migration_plan.md` (F-16 で実行)

## RiskMode (リスクモード、F-3)
- 内部値: `conservative` / `balanced` / `aggressive` (v9 から **完全維持、リネーム禁止**)
  - Aave MDD / Optimizer Allocator / Aave Risk Profile が文字列リテラル直参照
- 表示: `app.auth.models.RISK_MODE_JP_LABELS` (ローリスク / ミドルリスク / ハイリスク) で日本語化
- Phase 1 制限: `PHASE_1_ALLOWED_RISK_MODES = {CONSERVATIVE}`、API 層 (`PUT /auth/risk-mode`) で 403
- API レスポンス: UserResponse に `risk_mode_label` (computed_field) 追加、フロントは英語値→日本語化辞書を持たない
- 関連 endpoint: `GET /auth/risk-modes` (新規、全モード一覧 + Phase + 許可状態)
- NULL 4 ユーザーの 'conservative' 物理 UPDATE: `docs/47_users_risk_mode_migration_plan.md` (F-16 で実行)
