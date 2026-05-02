# Phase 2 AI Optimizer 設計書 (Draft)

**バージョン:** 0.1-draft  
**作成日:** 2026-05-02  
**スコープ:** Phase 1.5（2026年6月以降）で有効化される Lido/Pendle/Aave 配分最適化機能  
**ステータス:** ドラフト — PoC コード (`backend/app/ai/optimizer/`) と整合済み

---

## 1. 概要

### 1.1 目的

Phase 1 では Aave V3 のみで運用する。Phase 1.5 で Lido Finance および Pendle Finance を加えた
マルチプロトコル配分最適化（AI Optimizer）を有効化する。

AI Optimizer の役割は次の2つ:

1. **戦略比較**: 各プロトコルの Expected Net Benefit (ENB) を計算し、ランク付けする
2. **配分決定**: ユーザーのリスクモード（conservative / balanced / aggressive）に従い、
   最適なポートフォリオ配分を出力する

### 1.2 Phase 別スコープ

| Phase | スコープ | 有効化トリガー |
|-------|---------|--------------|
| Phase 1（現在） | Aave only (`conservative` 固定) | — |
| Phase 1.5（2026年6月〜） | Lido + Pendle + Aave 配分最適化 | Feature flag GID 1214462135512768 |
| Phase 2（2026年Q3〜） | リアルタイム APY フィード + 自動リバランス | 別タスクで検討 |

### 1.3 既存 PoC の位置付け

`backend/app/ai/optimizer/` に PoC 実装が完了している。本設計書はその実装を正規化・
拡張するための仕様文書。

```
backend/app/ai/optimizer/
├── schemas.py       — データモデル（Protocol, StrategyCandidate, NetBenefitResult 等）
├── net_benefit.py   — ENB 計算 (ExpectedNetBenefitCalculator)
├── strategy_scorer.py — プロトコル別スコアリング（PoC: 推定値使用）
├── allocator.py     — 配分決定 (PortfolioAllocator) + Risk Engine 連携
└── comparator.py    — 戦略比較レポート生成 (StrategyComparator)
```

---

## 2. 入力シグナル仕様

### 2.1 プロトコル APY

| プロトコル | データソース | 取得方法 | PoC 推定値 | 本番での取得先 |
|-----------|-----------|---------|-----------|-------------|
| Aave V3 USDC Supply | on-chain | `MonitoringService.get_health_factor()` / Aave GraphQL | 4.5% | Aave V3 Pool `getReserveData()` |
| Lido stETH Staking APR | on-chain + API | `AbstractLidoClient.get_staking_apr()` | 3.5% | Lido `getTotalPooledEther` + staking rewards index |
| Lido × Aave 複合 APY | 合算 | Lido APR + Aave stETH Supply APR | 5.0% (3.5 + 1.5) | 上記2つの合計 |
| Pendle PT Fixed APY | on-chain | `AbstractPendleClient.get_market_info()` → `implied_apy` | 5.2% | Pendle API v2 `/markets/{address}` |
| Pendle YT Leverage APY | 推定 | 投機的推定値 | 8.0% | Pendle API v2 + 利回り変動率 |

**注意:** PoC では `StrategyScorer` にハードコードされた推定値を使用。Phase 1.5 では
各プロトコルクライアントからリアルタイム値を取得する（`strategy_scorer.py` のリファクタリング必要）。

### 2.2 価格ボラティリティシグナル

| シグナル | 取得元 | ENB への影響 |
|---------|--------|------------|
| stETH/ETH ペグ乖離率 | `PegMonitor.get_peg_status()` | 乖離 > 2% → Lido risk_penalty 増加 |
| ETH 24h 価格変動 | `exchange/service.get_price_change_24h()` | 変動 > 10% → Pendle YT AVOID |
| ビットコイン相関 | AI 判定サービス経由（既存） | 将来拡張 |

### 2.3 Gas コスト予測

PoC では固定見積もりを使用:

| プロトコル | PoC Gas 見積もり (USD) | Phase 1.5 取得方法 |
|-----------|---------------------|------------------|
| Aave | $2.0 | Polygon/Base Gas Oracle |
| Lido | $5.0 | Ethereum Gas Oracle |
| Lido + Aave 複合 | $8.0 | 上記2段階の合計 |
| Pendle PT / YT | $10.0 | Arbitrum Gas Oracle |

### 2.4 リスク指標

| 指標 | 取得元 | 値の範囲 |
|-----|--------|---------|
| プロトコルヘルス | `ProtocolMonitor.check_all()` | RiskLevel: LOW/MEDIUM/HIGH/CRITICAL |
| 複合リスクスコア | `CompoundRiskAssessor.assess()` | 0-100 整数 |
| Pendle 満期残日数 | `MaturityManager.get_maturity_alerts()` | 正の整数（日） |
| Aave Health Factor | `MonitoringService.get_health_factor()` | Decimal（1.0 以上） |

---

## 3. 出力仕様

### 3.1 戦略比較出力（`StrategyComparison`）

```python
class StrategyComparison(BaseModel):
    candidates: list[NetBenefitResult]   # 全戦略のランク付き結果
    recommended: NetBenefitResult         # rank=1 の最良戦略
    idle_benefit: Decimal                 # 未投資の機会コスト (= 0)
    comparison_timestamp: str             # UTC ISO 形式
```

各 `NetBenefitResult` の主要フィールド:

| フィールド | 型 | 説明 |
|-----------|---|------|
| `protocol` | Protocol | プロトコル識別子 |
| `asset` | str | アセット (USDC / ETH / stETH) |
| `expected_net_benefit` | Decimal | ENB 値（USD、保有期間分） |
| `gross_yield` | Decimal | グロス利回り（USD） |
| `total_cost` | Decimal | ガス + ブリッジコスト合計 |
| `risk_adjusted_yield` | Decimal | リスク調整後利回り |
| `expected_apy` | Decimal | 元の期待 APY (%) |
| `rank` | int | 1 = 最良 |
| `recommendation` | Recommendation | STRONG_BUY / BUY / HOLD / AVOID |

### 3.2 配分推奨出力（`AllocationRecommendation`）

```python
class AllocationRecommendation(BaseModel):
    allocations: list[AllocationEntry]   # プロトコル別配分リスト
    total_expected_apy: Decimal          # 加重平均 APY
    total_risk_score: Decimal            # 加重平均リスクスコア
    explanation: str                     # 日本語説明（専門用語なし）
```

各 `AllocationEntry`:

| フィールド | 型 | 説明 |
|-----------|---|------|
| `protocol` | Protocol | 配分先プロトコル |
| `asset` | str | 対象アセット |
| `allocation_pct` | Decimal | 配分割合 (0-100) |
| `amount_usd` | Decimal | 配分金額（USD） |
| `expected_apy` | Decimal | 当該プロトコルの APY (%) |

### 3.3 推奨度判定ロジック

```
if net_benefit > gross_yield * 0.5  →  STRONG_BUY
elif net_benefit > 0                →  BUY
elif net_benefit > -total_cost      →  HOLD
else                                →  AVOID
```

AVOID プロトコルへの配分は 0% とし、余剰分は AAVE（次点: IDLE）に再配分。

---

## 4. アルゴリズム設計

### 4.1 ENB マルチプロトコル拡張式

#### 単一戦略の ENB 計算（既存実装 `net_benefit.py`）

```
gross_yield          = investment_usd × (expected_apy / 100) × (holding_days / 365)
total_cost           = gas_cost_usd + bridge_cost_usd
risk_penalty_amount  = gross_yield × risk_penalty
risk_adjusted_yield  = gross_yield − risk_penalty_amount
ENB                  = risk_adjusted_yield − total_cost
```

#### Phase 1.5 拡張: 動的 risk_penalty

Phase 1.5 では `risk_penalty` を `ProtocolMonitor` の動的スコアから算出する:

```
risk_level_score = {LOW: 0.05, MEDIUM: 0.25, HIGH: 0.60, CRITICAL: 0.90}
risk_penalty(protocol) = risk_level_score[ProtocolMonitor.check(protocol).risk_level]
```

ペグ乖離補正（Lido 系のみ）:

```
peg_deviation_pct = |1 - stETH/ETH ratio| × 100
if peg_deviation_pct > 2.0:
    risk_penalty += peg_deviation_pct / 100 × 0.5   # 補正係数 0.5
```

#### ポートフォリオ ENB（配分加重合計）

```
portfolio_ENB = Σ (allocation_pct[i] / 100) × ENB[i]   (全プロトコル i に対して)
```

### 4.2 配分決定アルゴリズム（リスクモード別テンプレート）

#### テンプレート定義（既存 `allocator.py`）

| リスクモード | AAVE | LIDO_AAVE | PENDLE_PT | PENDLE_YT | IDLE |
|------------|------|-----------|-----------|-----------|------|
| conservative | 95% | — | — | — | 5% |
| balanced | 60% | 25% | 10% | — | 5% |
| aggressive | 40% | 25% | 15% | 10% | 10% |

#### 制約条件（既存 `allocator.py: _apply_constraints`）

1. PENDLE_YT の配分上限: 10%
2. IDLE の配分下限: 5%
3. 単一プロトコル最大: 70%（conservative AAVE 95% は例外）
4. 配分合計: 100%（正規化）
5. AVOID プロトコルへの配分: 0%（AAVE または IDLE に再配分）

#### Phase 1.5 拡張: 動的制約

Pendle 満期 ≤ 7 日以内の場合:
- `maturity_days ≤ 7` → PENDLE_PT / PENDLE_YT を AVOID 扱い → 自動再配分
- `MaturityManager.get_maturity_alerts()` で判断

### 4.3 戦略比較フロー（疑似コード）

```python
async def optimize(request: OptimizerRequest) -> OptimizerResponse:
    # Step 1: APY フィード取得（Phase 1.5 以降: リアルタイム）
    candidates = await strategy_scorer.get_all_candidates_live()

    # Step 2: リスクスコア取得（Risk Engine 経由）
    risk_map = await _build_dynamic_risk_map()  # ProtocolMonitor.check_all()

    # Step 3: 各候補の ENB 計算 + ランク付け
    ranked_results = enb_calculator.rank_strategies(
        candidates, request.investment_usd, request.holding_days
    )

    # Step 4: 戦略比較レポート生成
    comparison = StrategyComparison(
        candidates=ranked_results,
        recommended=ranked_results[0],  # ENB 最大
        idle_benefit=Decimal("0"),
        comparison_timestamp=datetime.now(UTC).isoformat(),
    )

    # Step 5: 配分決定（リスクモード + AVOID 除外）
    allocation = await portfolio_allocator.allocate(
        ranked_results, request.investment_usd, request.risk_mode
    )

    # Step 6: 人間向けレポート生成
    report = comparator.generate_report(comparison, request.risk_mode)

    return OptimizerResponse(comparison=comparison, allocation=allocation, report=report)
```

---

## 5. バックエンド構造案

### 5.1 現状（PoC）vs Phase 1.5 の差分

| コンポーネント | 現状（PoC） | Phase 1.5 変更 |
|-------------|-----------|---------------|
| `strategy_scorer.py` | ハードコード推定値 | 各プロトコルクライアントから動的取得 |
| `allocator._build_dynamic_risk_map()` | `ProtocolMonitor` 呼び出し実装済み | そのまま使用 |
| `allocator._apply_constraints()` | 静的制約 | Pendle 満期チェック追加 |
| `net_benefit.py` | 固定 risk_penalty 使用 | 動的 risk_penalty（Risk Engine 連携） |
| API エンドポイント | 未実装（router なし） | `POST /api/optimizer/analyze` 追加 |
| Feature flag | なし | `PHASE2_OPTIMIZER_ENABLED` 環境変数 |

### 5.2 Phase 1.5 での追加・変更ファイル

```
backend/app/ai/optimizer/
├── schemas.py         — 変更なし（設計完了済み）
├── net_benefit.py     — 変更なし
├── allocator.py       — Pendle 満期チェック追加（_apply_constraints）
├── comparator.py      — 変更なし
├── strategy_scorer.py — リアルタイム APY 取得に変更（要実装）
└── router.py          — NEW: POST /api/optimizer/analyze エンドポイント
```

### 5.3 `POST /api/optimizer/analyze` エンドポイント仕様

**Request:**
```json
{
  "investment_usd": "10000.00",
  "risk_mode": "conservative",
  "holding_days": 30
}
```

**Response:**
```json
{
  "comparison": {
    "candidates": [...],
    "recommended": { "protocol": "aave", "rank": 1, ... },
    "idle_benefit": "0.00",
    "comparison_timestamp": "2026-06-01T00:00:00+00:00"
  },
  "allocation": {
    "allocations": [
      { "protocol": "aave", "asset": "USDC", "allocation_pct": "95.00", "amount_usd": "9500.00", "expected_apy": "4.50" },
      { "protocol": "idle", "asset": "CASH", "allocation_pct": "5.00", "amount_usd": "500.00", "expected_apy": "0.00" }
    ],
    "total_expected_apy": "4.275",
    "total_risk_score": "0.047",
    "explanation": "安全重視の配分です。預金のみで年率約4.3%の利回りが期待できます。\n\n※..."
  },
  "report": "=== 戦略比較レポート ===\n..."
}
```

**認証:** JWT 必須（`role: admin` または `role: partner`）

**Feature flag チェック（Phase 1）:**
```python
if risk_mode != "conservative" and not PHASE2_OPTIMIZER_ENABLED:
    raise HTTPException(403, "Phase 2 Optimizer is not enabled in this environment")
```

### 5.4 Feature Flag 設計

環境変数 `PHASE2_OPTIMIZER_ENABLED` で制御（デフォルト: `false`）:

| 環境 | 値 | 挙動 |
|-----|----|------|
| staging | `true` | balanced / aggressive モード有効 |
| production (Phase 1) | `false` | conservative のみ許可 |
| production (Phase 1.5〜) | `true` | 全モード有効 |

---

## 6. 検証計画

### 6.1 ユニットテスト（既存 PoC テスト拡張）

現在のテストファイル: `backend/tests/test_ai_optimizer_*.py`

追加テストケース:

| テスト | 検証内容 |
|-------|---------|
| `test_enb_dynamic_risk_penalty` | ProtocolMonitor HIGH → risk_penalty=0.60 で ENB 低下 |
| `test_pendle_maturity_avoid` | 満期 ≤ 7 日で PENDLE_PT が AVOID になること |
| `test_peg_deviation_adjustment` | stETH ペグ乖離 3% で Lido risk_penalty 補正 |
| `test_allocator_feature_flag_off` | `PHASE2_OPTIMIZER_ENABLED=false` で balanced が 403 |
| `test_portfolio_enb_sum` | portfolio_ENB = Σ(allocation_pct × ENB) の計算正確性 |
| `test_avoid_redistribution` | AVOID プロトコルが AAVE/IDLE に再配分される |

### 6.2 統合テスト

```
POST /api/optimizer/analyze (conservative) → 200, allocation=[AAVE 95%, IDLE 5%]
POST /api/optimizer/analyze (balanced, flag=off) → 403
POST /api/optimizer/analyze (balanced, flag=on) → 200, allocation=[AAVE≥60%, LIDO_AAVE>0]
```

### 6.3 E2E テスト（Playwright）

対象画面: `/user/strategies`（Phase 2 フロントエンド）

| ステップ | 確認内容 |
|---------|---------|
| ログイン → 戦略選択 | `/api/optimizer/analyze` が 200 を返すこと |
| リスクモード変更 | 配分グラフが更新されること |
| Phase 1 制限 | balanced/aggressive がグレーアウトまたは非表示 |

### 6.4 Staging 検証

1. `PHASE2_OPTIMIZER_ENABLED=true` で staging デプロイ
2. DummyLidoClient / DummyPendleClient で APY フィードをモック
3. `POST /api/optimizer/analyze` × 3 リスクモードで全ケースを確認
4. `ProtocolMonitor` が CRITICAL を返したときに AVOID が正しく発動することを確認

---

## 7. リスクと制約

### 7.1 技術リスク

| リスク | 影響度 | 対策 |
|-------|-------|------|
| 外部 APY フィード遅延 / 失敗 | 高 | `strategy_scorer` にフォールバック値（PoC 推定値）を保持 |
| Gas コスト急騰（Ethereum） | 中 | Gas Oracle でリアルタイム取得 + 閾値オーバーで AVOID |
| stETH ペグ乖離 > 5% | 高 | `PegMonitor` CRITICAL → Lido 系全 AVOID + 自動退避 |
| Pendle 満期切れ | 高 | `MaturityManager` で 7 日前アラート + 自動 AVOID |
| ProtocolMonitor 接続失敗 | 中 | フォールバック固定リスクスコア (`_FALLBACK_RISK_MAP`) |

### 7.2 財務リスク制約（既存 Security Rules と整合）

- Health Factor < 1.6 → HARD_STOP（AI Optimizer の出力を無効化）
- 単一取引: 総資産の 10% 以内（`exchange/service.py` の MAX_ORDER_USD_PCT）
- PENDLE_YT: 配分上限 10%（高レバレッジリスク）
- IDLE 最小 5% を常に確保（流動性バッファ）
- 全計算を `Decimal` 型で実施（`float` 禁止）

### 7.3 運用制約

- Phase 1 本番環境では `PHASE2_OPTIMIZER_ENABLED=false` を厳守
- PoC の `StrategyScorer` ハードコード値を本番で使用しない
- 自動リバランス実行は別タスク（Phase 2）—本設計書では配分推奨のみ

---

## 8. オープン課題

| No. | 課題 | 担当 | 優先度 | 期限 |
|----|------|------|-------|------|
| O-1 | `strategy_scorer.py` をリアルタイム APY 取得に変更 | 実装者 | P0 | Phase 1.5 開始前 |
| O-2 | `POST /api/optimizer/analyze` エンドポイント実装 | 実装者 | P0 | Phase 1.5 開始前 |
| O-3 | Gas Oracle 連携（Polygon/Base/Arbitrum 別対応） | 実装者 | P1 | Phase 1.5 |
| O-4 | Pendle 満期チェックを `_apply_constraints` に追加 | 実装者 | P1 | Phase 1.5 |
| O-5 | `PHASE2_OPTIMIZER_ENABLED` feature flag 実装と staging 検証 | 実装者 | P0 | Phase 1.5 開始前 |
| O-6 | portfolio_ENB を AI 判定（BUY/SELL/HOLD）のシグナルに統合する設計 | アーキテクト | P2 | Phase 2 |
| O-7 | 動的 risk_penalty を `net_benefit.py` の `calculate()` に組み込む方法の決定 | アーキテクト | P1 | Phase 1.5 |
| O-8 | Pendle YT の期待 APY 算出ロジック（現在は固定 8.0%）の改善 | 実装者 | P2 | Phase 2 |
| O-9 | フロントエンド `/user/strategies` の Phase 1 表示制御（balanced/aggressive グレーアウト） | フロントエンド | P1 | Phase 1.5 前 |
| O-10 | リアルタイム配分変更のログ記録と監査トレイル設計 | アーキテクト | P2 | Phase 2 |

---

## 付録 A: PoC コードと本設計書の対応

| 設計書セクション | 対応コードファイル |
|---------------|-----------------|
| §2.1 APY 入力 | `strategy_scorer.py` (PoC: 固定値) |
| §2.4 リスク指標 | `protocols/risk/protocol_monitor.py` |
| §3.1 戦略比較出力 | `schemas.py: StrategyComparison` |
| §3.2 配分推奨出力 | `schemas.py: AllocationRecommendation` |
| §4.1 ENB 計算式 | `net_benefit.py: ExpectedNetBenefitCalculator.calculate()` |
| §4.2 配分テンプレート | `allocator.py: _CONSERVATIVE/BALANCED/AGGRESSIVE_TEMPLATE` |
| §4.3 戦略比較フロー | `comparator.py: StrategyComparator.compare()` |
| §5.3 API 仕様 | 未実装（`router.py` 追加が必要）|

## 付録 B: 関連 Asana タスク

| GID | タイトル | 関係 |
|----|---------|------|
| 1214121040164875 | 本タスク（設計書作成） | — |
| 1214462135512768 | U-09 feature flag（Lido/Pendle hidden） | §5.4 Feature Flag 設計 |
| 1214462284653393 | Phase スコープ docs | §1.2 Phase 別スコープ |

## 付録 C: 参照ドキュメント

| ファイル | 関連セクション |
|---------|--------------|
| `docs/34_phase2_protocols_guide.md` | BaseProtocolClient インターフェース、プロトコル一覧 |
| `docs/13_security_design.md` | Health Factor 制約、セキュリティルール |
| `docs/07_aave_operation_logic.md` | Aave 運用ロジック、HF 閾値 |
| `docs/14_test_strategy.md` | テスト戦略、E2E 実行方法 |
