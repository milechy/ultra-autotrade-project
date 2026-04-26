# Fee Model v10 移行計画

> 最終更新: 2026-04-25
> 関連 Asana: F-0 (GID 1214120338928565)
> 関連ドキュメント: `docs/ops/02_db_tables.md` / `docs/ops/05_backend_modules_map.md`
> 注記: `docs/fee_model_v10_spec.md` は 2026-04-25 時点で **未作成**（山本さん側で起草予定）。本計画は既存実装の現状調査と移行戦略の選択肢提示までをスコープとする。

---

## 0. サマリー

### 既存 fee 実装は実は4系統存在
1. `backend/app/billing/` (ヘッジファンド方式 management+performance+HWM) — `/api/billing/*` 4 endpoints
2. `backend/app/billing/dynamic_fee.py` (GENERAL/UPPER × BEAR/STABLE/BULL の動的手数料) — `workflow.py` / `ai_judgment_scheduler.py` から本番ホットパスで呼出
3. `backend/app/aave/fee_router.py` + `aave/fee_calculator.py` (AUMベース、CSV出力) — `/api/fees/*` 2 endpoints
4. `backend/app/users/fee_service.py` (tier別手数料率レンジ定義のみ、`/api/users/fees` 等の参照系)

加えて取引所手数料の `backend/app/exchange/fee_calculator.py`(maker/taker)があるが、これは取引所手数料レイヤーで本計画のスコープ外。

### 本番DB現状（2026-04-25 read-only調査）
- `fee_configs` / `fee_calculations` / `high_water_marks`: **全て 0 行**（既存billingヘッジファンド方式は本番未稼働）
- `users.tier`: 全6人 `GENERAL`、UPPERユーザーゼロ
- `users.risk_mode`: `conservative` × 2人、NULL × 4人
- `fee_transactions` テーブル: **未作成**

### 推奨移行戦略
**Option A（既存billing廃止 + dynamic_fee統合 + v10新規実装で完全置換）**

理由:
- billingヘッジファンド方式は本番1度も計算実行されておらず、捨てるデータ・履歴がゼロ
- dynamic_fee.py は本番呼出経路にあるが、proposals が 0 件 = 計算結果は一度も確定していない
- 新規実装と既存実装を並行稼働させると運用複雑度が倍になる（Phase1中で時期尚早）

### 山本さん本番テストへの影響
- 本計画策定（docs追加 + PR）= **影響ゼロ**（read-only調査と新規ドキュメントのみ）
- 実装 F-1〜F-16 段階の影響は §5 で個別評価

---

## 1. 現状マップ

### 1.1 backend/app/billing/ (ヘッジファンド方式)

| 項目 | 内容 |
|------|------|
| 用途 | `management_fee` (年率0.5%) + `performance_fee` (10%) + HWM (High Water Mark) 方式 |
| ファイル | `models.py` / `router.py` / `service.py` / `schemas.py` |
| テーブル | `fee_configs` / `fee_calculations` / `high_water_marks` |
| 呼出元 | `app.include_router(billing_router)` (`main.py:230`) のみ。**バックグラウンド呼出ゼロ**（手動 `/api/billing/batch/daily` POST 経由のみ） |
| 本番DB状態 | 3テーブルとも **0行**。日次バッチ未実行 |
| API | GET `/api/billing/fees` / GET `/api/billing/summary` / POST `/api/billing/batch/daily`（admin） / GET `/api/billing/config` |
| デフォルト値 | management_fee_rate=0.5%, performance_fee_rate=10%, minimum_aum=$3000, HWM=enabled |

### 1.2 backend/app/billing/dynamic_fee.py (動的手数料 — 本番ホットパス)

| 項目 | 内容 |
|------|------|
| 用途 | 取引時点の動的手数料計算。新方式 `calculate_fee_by_market()` (市場×ティア6マトリクス) と旧方式 `calculate_dynamic_fee()` (ENB比率) の2関数 |
| ティア×市場マトリクス | GENERAL: 3-15% / UPPER: 10-25%、BEAR/STABLE/BULL の3市場区分（APY < 3% / 3-6% / > 6%） |
| 呼出元 | `automation/workflow.py:757` (auto_execute以外の経路) / `automation/ai_judgment_scheduler.py:154` (Proposal生成時) |
| 本番影響 | proposals テーブルが空のため、計算結果が確定したケースは過去14日 0件。**コードは生きているが結果は積まれていない** |
| 経費ガード | 純利益 (expected_profit - fixed_cost) ≤ 0 → `should_trade=False` でHOLDに転換 |

### 1.3 RiskModeUpdateRequest (auth/schemas.py + Aave/Optimizer統合)

| 項目 | 内容 |
|------|------|
| 値 | `conservative` / `balanced` / `aggressive`（pattern enum） |
| API | GET `/auth/risk-mode` / PUT `/auth/risk-mode` |
| 用途1: AI Optimizer | `optimizer/allocator.py:96-104` で配分戦略決定（conservative→USDC寄せ等） |
| 用途2: MDD閾値 | `aave/mdd_tracker.py:11-14` で損失閾値（-10%/-20%/-30% hard_stop） |
| 用途3: Aave Risk Profile | `aave/risk_profile.py:35` で Health Factor閾値・許可資産 |
| **v10との関係** | v10「ローリスク/ミドル/ハイ」と概念ほぼ一致。**enum値リネーム不可（Aave/Optimizer 全箇所影響）。日本語ラベルだけ追加 or 1:1 マッピング辞書で吸収するのが現実解** |
| ドキュメント不一致 | `docs/ops/02_db_tables.md:44` と `docs/ops/05_backend_modules_map.md:70` は `moderate` 表記。コード実装は `balanced`。docs側を修正必要（別タスク） |

### 1.4 既存 fee 関連 API endpoints (重複整理)

| endpoint | router | 役割 | v10で残す? |
|----------|--------|------|------------|
| GET `/api/billing/fees` | billing/router.py | ユーザー手数料履歴 (HWM方式) | △ 名前空間統合 |
| GET `/api/billing/summary` | billing/router.py | ユーザー手数料累計 | △ 名前空間統合 |
| POST `/api/billing/batch/daily` | billing/router.py | 日次バッチ (admin) | × 廃止 (v10は月次バッチ) |
| GET `/api/billing/config` | billing/router.py | FeeConfig 取得 | × 廃止 (v10新spec) |
| GET `/api/fees/calculate` | aave/fee_router.py | AUM+利益+日数 → 手数料計算 (CSV系) | × 廃止 (v10と概念ぶれ) |
| GET `/api/fees/schedule` | aave/fee_router.py | 手数料スケジュール表示 | × 廃止 |
| GET `/api/users/fees` 等 | users/fee_service.py 経由 | tier別レンジ定義参照 | △ v10 fee_configs に置換 |

**結論**: `/api/billing/*` と `/api/fees/*` は **prefix 重複** しており、v10では `/api/fees/*` 1系統に統合するのが望ましい（F-8 で対応）。

---

## 2. v10 想定要件との差分

> v10 spec.md が未作成のため、Asana F-1〜F-16 のタスク名と既存実装からv10要件を逆算した推定値を記載。spec.md 確定後に再校正必要。

### 2.1 テーブル

| v10想定 | 既存 | 推奨アクション |
|---------|------|----------------|
| `fee_configs` (リスクモード × tier の手数料率テーブル) | あり（HWM方式の単一行設定） | **スキーマ全面置換** (DROP→CREATE)、本番0行のため安全 |
| `fee_transactions` (月次計算結果) | **未作成** | F-1 で新規 CREATE |
| (使わない想定) | `fee_calculations` | 廃止対象 |
| (使わない想定) | `high_water_marks` | 廃止対象 |

### 2.2 users.tier

| 項目 | 状態 |
|------|------|
| カラム実在 | **YES** (String(20), DEFAULT='GENERAL', NOT NULL) |
| 値分布 | 全6人 GENERAL のみ |
| docs/ops/05 記載 | 「未適用」← **誤り**。要修正（別タスク） |
| v10想定 | 3層 (一般/ミドル/アッパー) |
| マイグレーション | F-2 で enum拡張 (GENERAL/MIDDLE/UPPER 等)。既存6人は GENERAL のまま |

### 2.3 users.risk_mode

| 項目 | 状態 |
|------|------|
| カラム実在 | **YES** (String(20), nullable) |
| 値分布 | conservative=2 / NULL=4 |
| 既存値 | conservative / balanced / aggressive (pattern enum 強制) |
| v10想定 | ローリスク / ミドル / アッパー (3段) |
| マイグレーション | **enum値はリネーム不可**（Aave/Optimizer/MDD 全箇所が `balanced` を直接参照）。表示ラベルだけ日本語化、内部値は維持 |
| NULL処理 | 4人がNULLのままだとMDD閾値・Aave Risk Profile が `conservative` フォールバック。v10で `NOT NULL DEFAULT 'conservative'` に変更検討 (F-3) |

---

## 3. 移行戦略 (Option A/B/C)

### Option A — 既存billing廃止、v10新規実装で完全置換 ★★★ **推奨**

**メリット**
- 本番billingテーブル 0 行のためデータ移行ゼロ
- コード単純化（dynamic_fee.py を v10 fee_calculator に統合）
- API名前空間が `/api/fees/*` 1系統に整理される

**デメリット**
- billing/router.py の 4 endpoints と aave/fee_router.py の 2 endpoints をフロントから一括差し替え必要
- `dynamic_fee.calculate_fee_by_market` を呼ぶ workflow.py / ai_judgment_scheduler.py の 2 箇所を v10 API へ繋ぎ替え

**適用条件**
- Phase 1 中（実資金フィー徴収開始前）。本番に手数料履歴データなし
- ✅ 現状すべて該当 → **Aを推奨**

### Option B — 既存billingをv10 wrapper化 ★

**メリット** API互換性維持

**デメリット** 二重実装、テスト工数倍、最終的にAに戻すコスト発生

**適用条件** 既存billingに本番ユーザー履歴が積まれている場合 → ❌ 該当せず

### Option C — 並行稼働 + feature flag ★★

**メリット** 段階的切替可、ロールバック容易

**デメリット** 本番複雑化、テスト工数倍

**適用条件** 本番ユーザー資金規模が大きい・誤計算で実害発生する状態 → ❌ 該当せず（山本さんテスト中、Phase 1）

### **推奨: Option A**

根拠: billing 3テーブルが本番0行 + dynamic_fee の確定計算結果も0件 + tier=GENERAL × 6人のみ。捨てるデータがないため Option B/C の延命価値ゼロ。

---

## 4. F-1〜F-16 タスク影響と due 調整提案

> 全タスク Phase 1 (山本さんテスト中) スコープ。実資金フィー徴収開始は F-15 (山本さんレビュー) 後。
> due は claude.ai 承認後に Asana 反映する想定。下記は claude.ai への提案値。

| GID | F# | タスク名（推定） | 戦略影響 / 注意点 | 提案 due |
|-----|----|------------------|-------------------|----------|
| 1214120248239215 | F-1 | fee_configs/fee_transactions DDL | 既存 fee_configs (0行) を DROP → CREATE。fee_transactions 新規 CREATE。Hetzner手動 ALTER 方式 | 2026-04-29 |
| 1214120248237710 | F-2 | InvestmentTier 3層化 | enum 拡張 (GENERAL → GENERAL/MIDDLE/UPPER 等)。既存6人 GENERAL のまま | 2026-04-30 |
| 1214120401362419 | F-3 | RiskMode enum (v10) | **既存 risk_mode 列の enum 値はリネーム不可**。日本語ラベル辞書だけ新設。NULL 4人を 'conservative' で埋める | 2026-04-30 |
| 1214120401381545 | F-4 | FeeConfig seed data | F-1 完了後。リスクモード × tier の手数料率マトリクス投入 | 2026-05-01 |
| 1214120371502936 | F-5 | fee_calculator.py コア | 新規 `backend/app/fees/calculator.py`。dynamic_fee.py の `calculate_fee_by_market` をベースに統合 | 2026-05-04 |
| 1214120371503067 | F-6 | AI判断ロジック統合 | workflow.py:757, ai_judgment_scheduler.py:154 の dynamic_fee import を v10 API に差し替え (注[1]参照) | 2026-05-05 |
| 1214120401388139 | F-7 | 月末バッチ | 既存 `POST /api/billing/batch/daily` は **廃止**。v10 は月次。`scheduled_tasks.py` に新規ジョブ | 2026-05-06 |
| 1214120371503131 | F-8 | fees.py API | `/api/billing/*` 4 endpoints と `/api/fees/*` 2 endpoints を `/api/fees/*` 1系統に統合 | 2026-05-07 |
| 1214120371503003 | F-9 | 経費マークアップ | 固定経費 $0.27/トレード (現状 dynamic_fee デフォルト) を v10 で再評価 | 2026-05-08 |
| 1214120353305925 | F-10 | リスクモード選択UI | F-3 完了後。**既存 PUT `/auth/risk-mode` は維持**、UI ラベルだけ日本語化 | 2026-05-08 |
| 1214120401388268 | F-11 | ダッシュボード手数料表示 | 既存 GET `/api/billing/summary` を v10 GET `/api/fees/summary` に置き換え | 2026-05-11 |
| 1214120338928693 | F-12 | 管理者画面 fee管理タブ | FeeConfig 編集UI。既存 GET `/api/billing/config` 廃止に伴うフロント差し替え | 2026-05-12 |
| 1214120401381933 | F-13 | v9 fee 段階廃止 | **Option A 採用なら DROP TABLE billing系3テーブル + billing/ ディレクトリ削除に変更**。タスク名 「廃止」→「物理削除」へ更新 | 2026-05-13 |
| 1214120353305989 | F-14 | Playwright E2E | F-1〜F-13 完了後。フィー画面 UI / API レグレッション | 2026-05-14 |
| 1214120401388204 | F-15 | 山本さんレビュー | F-14 完了後。本番デプロイ前承認 | 2026-05-15 |
| 1214120338926364 | F-16 | v10 本番リリース | F-15 完了後。Hetzner ALTER TABLE → コードデプロイ | 2026-05-18 |

> **注[1]**: F-6 解釈A確定 (2026-04-26 claude.ai判断)。`docs/fee_model_v10_spec.md` §4 未作成のため、F-6 スコープは以下に限定:
>
> - `workflow.py` / `ai_judgment_scheduler.py` の tier 正規化 (`normalize_tier()` ヘルパー導入、`auth/models.py`)
> - `workflow.py` の `tier="GENERAL"` ハードコード除去 (`user_id` 配線で `user.tier` 経由)
> - `current_apy` バグの TODO 化 (修正は P0 タスク 1214279097935851 で MarketContext に Aave データ注入時に対応)
>
> 月次 `FeeCalculator` 統合は **F-7 担当**。Phase 1 中は trade-time の `should_trade` gate を `calculate_fee_by_market` で維持する。

---

## 5. 山本さん連絡要否

**結論: 不要（現段階では）**

根拠:
- 本計画 = ドキュメント追加 PR のみ。山本さんの本番テストフロー（https://app.ultra-auto-trade.com/login）に **影響ゼロ**
- F-3 (RiskMode enum) で UI に「リスクモード選択画面」が出た段階で連絡必要（F-10 着手前）
- F-15 (山本さんレビュー) は明示的に承認依頼が組み込み済み

**連絡が必要になるトリガー**:
- F-13 (v9 fee 段階廃止) 着手時 = `/api/billing/*` が本番から消える → API 互換性ブレイク
  - ただし山本さんはフィー UI を見ておらず（proposals 0 件）影響観測不能。**事前連絡推奨だが必須ではない**

---

## 6. 次のアクション

1. ✅ 本 plan を PR で main にマージ
2. ⏸ claude.ai に本 plan の戦略 (Option A) 承認依頼
3. ⏸ 承認後、Asana F-1〜F-16 タスク notes を Option A 前提で更新（**CLI で勝手に更新しない**、本タスクのスコープ外）
4. ⏸ F-0 クローズ → F-1 (fee_configs/fee_transactions DDL) 着手
5. 別タスク提案:
   - `docs/ops/02_db_tables.md` `moderate` → `balanced` 修正
   - `docs/ops/05_backend_modules_map.md` 「tier 未適用」記載削除（実態は適用済み）
   - `docs/fee_model_v10_spec.md` 起草（山本さん）

---

## 付録 A: 本番DB read-only 調査結果（2026-04-25 09:15 JST）

```
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' AND table_name IN
  ('fee_configs','fee_calculations','fee_transactions','high_water_marks');
   → fee_calculations, fee_configs, high_water_marks (fee_transactions 不在)

SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns WHERE table_name='users'
  AND column_name IN ('tier','last_judgment_at','execution_policy','risk_mode');
   → execution_policy: varchar, default 'auto_execute', nullable
     last_judgment_at: timestamptz, nullable
     risk_mode:        varchar, no default, nullable
     tier:             varchar, default 'GENERAL', NOT NULL

SELECT tier, COUNT(*) FROM users GROUP BY tier;
   → GENERAL: 6

SELECT risk_mode, COUNT(*) FROM users GROUP BY risk_mode;
   → conservative: 2, NULL: 4

SELECT * FROM fee_configs;          → 0 rows
SELECT period_type, COUNT(*) FROM fee_calculations GROUP BY period_type;  → 0 rows
SELECT COUNT(*) FROM high_water_marks;   → 0 rows
```

## 付録 B: 既存 dynamic_fee 呼出経路（本番ホットパス）

```
backend/app/automation/workflow.py:757
  from app.billing.dynamic_fee import calculate_fee_by_market
  → require_approval / proposal_only 経路で Proposal 生成時に手数料試算
  → should_trade=False なら HOLD に転換

backend/app/automation/ai_judgment_scheduler.py:154
  from app.billing.dynamic_fee import calculate_fee_by_market
  → スケジューラーが active users に Proposal 自動生成時、tier別手数料計算
  → user.tier をそのまま渡す（GENERAL/UPPER 以外で ValueError 発生リスク）
```

## 付録 C: docs/ops 整合性問題（別タスク化推奨）

| 場所 | 記載内容 | 実態 | 修正方針 |
|------|----------|------|----------|
| `docs/ops/02_db_tables.md:44` | `risk_mode: conservative/moderate/aggressive` | 実装は `balanced` | `moderate` → `balanced` |
| `docs/ops/05_backend_modules_map.md:70` | 同上 | 同上 | 同上 |
| `docs/ops/05_backend_modules_map.md:244-247` | 「tier カラム未適用」 | 本番DBに存在 (DEFAULT 'GENERAL', NOT NULL) | 該当ブロック削除 |
