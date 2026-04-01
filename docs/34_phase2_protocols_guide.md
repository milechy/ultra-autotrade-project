# Phase 2 マルチプロトコル連携 技術ガイド

## 1. 概要

### Phase 2 の目的

Phase 1（Aave V3単独）から、Lido Finance・Pendle Finance との連携による
マルチプロトコル利回り最適化への拡張。

AI Optimizer（Expected Net Benefit）がリスクスコアと期待APYを統合し、
最適な配分を自動決定する。

### アーキテクチャ

```
BaseProtocolClient（OCP準拠の共通インターフェース）
├── AbstractLidoClient → LidoWebClient / MockLidoClient
├── AbstractPendleClient → PendleWebClient / MockPendleClient
└── （今後の拡張プロトコルも同インターフェースを実装）

AI Optimizer（app/ai/optimizer/）
├── net_benefit.py — Expected Net Benefit 計算
├── strategy_scorer.py — プロトコル別スコアリング
├── comparator.py — 戦略比較
└── allocator.py — 配分決定（Risk Engine連携）

Risk Engine（app/protocols/risk/）
├── protocol_monitor.py — プロトコル一括ヘルスチェック
├── compound_risk.py — 複合リスク評価
├── peg_monitor.py — stETH/ETHペグ監視
├── maturity_manager.py — Pendle満期管理
└── auto_evacuate.py — 自動退避ロジック
```

---

## 2. プロトコル一覧

| プロトコル | ステータス | 主な用途 | APY目安 | リスク |
|---|---|---|---|---|
| Aave V3 | Phase 1（稼働中） | USDC Supply/Withdraw | 3-5% | 低 |
| Lido Finance | Phase 2（PoC完了） | stETH ステーキング | 3.5-4% | 中 |
| Pendle Finance | Phase 2（PoC完了） | PT固定利回り / YTレバレッジ | 5-15% | 中〜高 |

---

## 3. BaseProtocolClient インターフェース

`backend/app/protocols/base.py` で定義する共通インターフェース。

### データクラス

| クラス | フィールド | 説明 |
|---|---|---|
| `ProtocolPosition` | `protocol_name`, `asset`, `balance: Decimal`, `value_usd: Decimal` | プロトコル上のポジション情報 |
| `ProtocolHealthMetrics` | `protocol_name`, `is_healthy`, `risk_score: Decimal`, `details: dict[str, str]` | ヘルスメトリクス（risk_score: 0.0=安全〜1.0=危険） |
| `TransactionResult` | `success`, `tx_hash`, `amount: Decimal`, `error` | トランザクション実行結果 |

### 共通メソッド（7つの抽象メソッド）

```python
class BaseProtocolClient(ABC):
    @abstractmethod
    def get_protocol_name(self) -> str:
        """プロトコル名を返す。"""

    @abstractmethod
    def get_supported_assets(self) -> list[str]:
        """サポートするアセット一覧を返す。"""

    @abstractmethod
    async def get_current_apy(self) -> Decimal:
        """現在の APY（年率、%単位）を返す。"""

    @abstractmethod
    async def supply(self, amount: Decimal, asset: str) -> TransactionResult:
        """アセットを預け入れる。"""

    @abstractmethod
    async def withdraw(self, amount: Decimal, asset: str) -> TransactionResult:
        """アセットを引き出す。"""

    @abstractmethod
    async def get_position(self) -> ProtocolPosition:
        """現在のポジション情報を返す。"""

    @abstractmethod
    async def get_health_metrics(self) -> ProtocolHealthMetrics:
        """プロトコルのヘルスメトリクスを返す。"""
```

### 新プロトコル追加手順

1. `app/protocols/<protocol>/` ディレクトリを作成
2. `AbstractXxxClient(BaseProtocolClient)` を実装
3. 7つの抽象メソッドを全て実装
4. `tests/protocols/test_<protocol>/` にテストを追加
5. `app/protocols/risk/protocol_monitor.py` にヘルスチェックを追加

---

## 4. AI Optimizer（Expected Net Benefit）

### ENB計算ロジック

`backend/app/ai/optimizer/net_benefit.py` の `ExpectedNetBenefitCalculator` が実装。

```
gross_yield = investment_usd × (expected_apy / 100) × (holding_days / 365)
total_cost = gas_cost_usd + bridge_cost_usd
risk_penalty_amount = gross_yield × risk_penalty
risk_adjusted_yield = gross_yield - risk_penalty_amount
net_benefit = risk_adjusted_yield - total_cost
```

**推奨度判定ロジック:**

| 条件 | 推奨度 |
|---|---|
| `net_benefit > gross_yield × 0.5` | `STRONG_BUY` |
| `net_benefit > 0` | `BUY` |
| `net_benefit > -total_cost` | `HOLD` |
| それ以外 | `AVOID` |

### 配分テンプレート（`allocator.py`）

| リスクモード | 配分 |
|---|---|
| conservative | AAVE: 95%、IDLE: 5% |
| balanced | AAVE: 60%、LIDO_AAVE: 25%、PENDLE_PT: 10%、IDLE: 5% |
| aggressive | AAVE: 40%、LIDO_AAVE: 25%、PENDLE_PT: 15%、PENDLE_YT: 10%、IDLE: 10% |

**制約:**
- 単一プロトコル最大 70%（conservative の AAVE 95% は例外）
- PENDLE_YT は常に <= 10%
- IDLE は常に >= 5%
- 推奨度 `AVOID` のプロトコルには配分しない（余剰分は AAVE または IDLE に再配分）

### Risk Engine連携

`_calculate_risk_score()` → `_build_dynamic_risk_map()` を呼び出して動的リスクスコアを取得する。

```python
# 動的スコア取得の動作（allocator.py）
成功: logger.debug("using dynamic risk score from risk engine: %s", risk_map)
失敗: logger.warning("risk engine unavailable, using fallback risk scores: %s", exc)
      → フォールバック固定値を使用（安全側）
```

**フォールバックリスクスコア（固定値）:**

| プロトコル | フォールバック値 |
|---|---|
| AAVE | 0.05 |
| LIDO | 0.15 |
| LIDO_AAVE | 0.20 |
| PENDLE_PT | 0.10 |
| PENDLE_YT | 0.30 |
| IDLE | 0.00 |

**リスクレベル → スコア変換:**

| リスクレベル | スコア |
|---|---|
| low | 0.05 |
| medium | 0.25 |
| high | 0.60 |
| critical | 0.90 |

---

## 5. Risk Engine

### 主要コンポーネント

#### `ProtocolMonitor`（`protocol_monitor.py`）

全プロトコルのヘルスチェックを一括実行する。

| メソッド | 説明 |
|---|---|
| `check_aave_health()` | Aave V3 ヘルスチェック（PoC: TVL $10B、risk=LOW の固定値） |
| `check_lido_health()` | Lido ヘルスチェック（APR・stETH/ETH レート取得） |
| `check_pendle_health()` | Pendle ヘルスチェック（マーケット情報・implied APY 確認） |
| `check_all()` | 上記3つを順次実行してリストで返す |

#### `PegMonitor`（`peg_monitor.py`）

stETH/ETH のペグ乖離を監視する。

**乖離率によるリスク分類:**

| 乖離率 | リスクレベル |
|---|---|
| < 0.5% | LOW |
| 0.5% 以上 1.0% 未満 | MEDIUM |
| 1.0% 以上 2.0% 未満 | HIGH |
| 2.0% 以上 | CRITICAL |

Lido ヘルスチェック（`check_lido_health`）では乖離 > 2% で HIGH、`PegMonitor` は独立した詳細分類を持つ。

#### `MaturityManager`（`maturity_manager.py`）

Pendle マーケットの満期状況を管理する。

**残り日数によるリスク分類:**

| 残り日数 | リスクレベル | アクション |
|---|---|---|
| 30日以上 | LOW | none |
| 14〜29日 | MEDIUM | monitor |
| 7〜13日 | HIGH | prepare_exit |
| 7日未満 | CRITICAL | exit_now |

#### `CompoundRiskAssessor`（`compound_risk.py`）

複合リスクスコアを計算する（0〜100）。

**スコア算出（合計最大100）:**

| コンポーネント | LOW | MEDIUM | HIGH | CRITICAL |
|---|---|---|---|---|
| プロトコル（最大40） | 0 | 5 | 15 | 40 |
| ペグ（最大30） | 0 | 5 | 15 | 30 |
| 満期（最大30） | 0 | 5 | 15 | 30 |

- いずれかのコンポーネントが CRITICAL → 合計スコアを最低80に切り上げ
- スコア >= 80 → `should_evacuate = True`（自動退避トリガー）

**全体リスクレベル変換:**

| スコア | リスクレベル |
|---|---|
| 0〜20 | LOW |
| 21〜40 | MEDIUM |
| 41〜70 | HIGH |
| 71〜100 | CRITICAL |

---

## 6. テスト結果

| カテゴリ | テストファイル数 | pass数 |
|---|---|---|
| Lido連携 | 4ファイル | 56 |
| Pendle連携 | 5ファイル | 86 |
| AI Optimizer | 5ファイル（+統合テスト） | 69 |
| Risk Engine | 5ファイル（+統合テスト） | 187 |
| **合計（全テスト）** | — | **1754** |

---

## 7. フロントエンド

| ページ | URL | 対象 | 状態 |
|---|---|---|---|
| 戦略選択 | /user/strategies | 一般ユーザー | Phase 2実装済み |
| ヘルスモニター | /admin/protocols | 管理者 | Phase 2実装済み |

---

## 8. 既知の制限と今後の課題

- Lido/Pendle は現状 PoC（テストネット未検証）
- Aave `check_aave_health` は PoC 固定値（MonitoringService 連携は本番化時に実装）
- C-1/C-2 は実装完了、テスター運用後に dev マージ予定
- E2E テスト（Playwright）は dev マージ後に実施
- `_build_dynamic_risk_map` はイベントループが実行中の場合はスキップ（`None` を返す）→ フォールバック固定値使用
