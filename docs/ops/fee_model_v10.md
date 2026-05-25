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

## Tier × 料率 / Yield Cap マトリクス (P0-18、launch 値)

> **SSOT: `backend/app/fees/constants.py`**。値変更時は本ドキュメントと
> `scripts/seed_fee_config_v10.py` の 3 箇所を同時更新する (前者を import するだけ
> で後者は自動同期、本ドキュメントは手動)。整合性は `tests/fees/test_constants.py` が機械検査。

| Tier | JPY 境界 | 月次料率 | 月次 yield cap |
|---|---|---|---|
| **LOWER** | 〜 1,000,000 | 30% | 1.8% |
| **MIDDLE** | 1,000,001 〜 10,000,000 | 25% | 2.3% |
| **UPPER** | 10,000,001 〜 | 20% | 3.0% |

- アフィリエイト還元率: **30%** (`AFFILIATE_RATE`)
- 経費マークアップ: 既定 **OFF** (`EXPENSE_MARKUP_ENABLED_DEFAULT=False`)
- Invariant: `tier_fee_rates` は単調 **減少** (上位ほど低料率)、`tier_monthly_yield_caps` は単調 **増加** (上位ほど高 cap)

Launch 反映手順: `docs/48_fee_config_seed_runbook.md` の 3 段プロンプトに従い `seed_fee_config_v10.py` を実行 (F-16)。
