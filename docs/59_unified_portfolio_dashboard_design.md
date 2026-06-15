# 59_unified_portfolio_dashboard_design.md
# 統合ポートフォリオダッシュボード 設計書

作成日: 2026-06-15
Asana: feat/unified-portfolio-aggregation-design
ブランチ: feat/unified-portfolio-aggregation-design
関連docs: docs/04_api_design.md / docs/13_security_design.md / docs/34_phase2_protocols_guide.md
関連モジュール: backend/app/portfolio/ / backend/app/aave/client.py / backend/app/partner/wallet_balance_schemas.py / backend/app/exchange/schemas.py

> **Status: DRAFT (Phase 1 / 設計 + 純粋集約関数のみ)**。本ドキュメントは設計の正本であり、
> 実API呼出endpoint・frontend実装・main.py配線は後続HUMANレビュースライスで行う。

---

## 0. Summary

Ultra AutoTrade は現在ポートフォリオをAave V3 単一ソース（履歴スナップショット）のみで管理している
(`backend/app/portfolio/` モジュール)。実際の資産は以下3ソースに分散している:

1. **Aave V3** — 担保・借入・純資産 (DeFi)
2. **Privy ウォレット** — Base mainnet 上の ETH + USDC 現物 (Aave supply 分を含まない)
3. **Bybit CEX** — USDT 残高 (中央集権取引所)

本設計書は「統合ポートフォリオビュー」として3ソースを横断集約する方式を定義する。

---

## 1. 現状把握 (実コード grep / 行番号付き)

### 1.1 Aave AccountData — `backend/app/aave/client.py`

| 行 | フィールド | 型 | 備考 |
|---|---|---|---|
| L235 | `class AccountData` | dataclass | |
| L238 | `total_collateral_usd` | `Decimal` | Aave V3 Pool getUserAccountData 由来 |
| L239 | `total_debt_usd` | `Decimal` | |
| L240 | `available_borrows_usd` | `Decimal` | |
| L241 | `health_factor` | `Decimal` | `Decimal("inf")` が来ることがある (L696) |

ネットワーク: 本番は Base mainnet / staging は Base Sepolia。`AAVE_NETWORK` env で切替。

### 1.2 Privy Wallet Balance — `backend/app/partner/wallet_balance_schemas.py`

| 行 | フィールド | 型 | 備考 |
|---|---|---|---|
| L19 | `class WalletBalanceResponse` | Pydantic BaseModel | |
| L28 | `eth_usd_value` | `Decimal` | eth_balance * eth_usd_price |
| L31 | `usdc_usd_value` | `Decimal` | usdc_balance (1:1) |
| L32 | `total_usd` | `Decimal` | eth_usd_value + usdc_usd_value |

**重要**: `backend/app/partner/wallet_balance_service.py` L13 に明記 —
「NOTE: Aave supply 分は **含まない**。ウォレットに「入っている」分のみ。」

チェーン: Base mainnet 固定 (`backend/app/partner/wallet_balance_service.py` L31-36)。
fail-open 設計: `_all_fallback_response()` (L198) で全フィールド Decimal("0") を返す。

### 1.3 Bybit CEX Exchange Status — `backend/app/exchange/schemas.py`

| 行 | フィールド | 型 | 備考 |
|---|---|---|---|
| L107 | `class ExchangeStatusResponse` | Pydantic BaseModel | |
| L122 | `balance_usdt` | `Optional[Decimal]` | fetch_balance() 失敗時は None |

`backend/app/exchange/service.py` L255: `balance_usdt` は `None` の場合がある。
USDT ≈ USD 1:1 として換算する (stablecoin 前提)。

---

## 2. 統合スキーマ設計

### 2.1 設計原則

- **Decimal-only**: 全金融計算は `Decimal` 型。`float` 使用禁止 (Security Rule 11)
- **fail-open per source**: 各ソースが利用不可でも他ソースを表示し続ける (`available: bool`)
- **二重計上なし**: Wallet残高はAave supply分を含まない (wallet_balance_service.py L13 確認済み)
- **HFはAave由来透過**: Health Factor は Aave ソースが存在する場合のみ表示。集約値は算出しない

### 2.2 UnifiedPortfolioInput (集約関数への入力)

```
UnifiedPortfolioInput:
  aave:   Optional[SourceBalance]   # 欠落 = Aave取得失敗
  wallet: Optional[SourceBalance]   # 欠落 = Wallet取得失敗
  cex:    Optional[SourceBalance]   # 欠落 = CEX取得失敗
```

### 2.3 SourceBalance (ソース別残高)

```
SourceBalance:
  source:        Literal["aave", "wallet", "cex"]
  total_usd:     Decimal                  # ソース内合計USD
  available:     bool                     # データ取得成功フラグ
  supply_usd:    Optional[Decimal]        # Aave専用: 担保総額
  borrow_usd:    Optional[Decimal]        # Aave専用: 借入総額
  health_factor: Optional[Decimal]        # Aave専用: 健全性指標
```

Aave の `total_usd` は `total_collateral_usd - total_debt_usd` (純資産)。

### 2.4 UnifiedPortfolioView (集約出力)

```
UnifiedPortfolioView:
  grand_total_usd:    Decimal                  # 3ソース合算USD
  aave_net_usd:       Decimal                  # Aave 純資産 (0 if unavailable)
  wallet_usd:         Decimal                  # Wallet 残高 (0 if unavailable)
  cex_usd:            Decimal                  # CEX 残高 (0 if unavailable)
  health_factor:      Optional[Decimal]        # Aave由来のみ
  allocations:        list[SourceAllocation]   # ソース別配分
  sources_available:  int                      # 正常取得ソース数 (0-3)
  sources_total:      int                      # 総ソース数 (常に3)
  degraded:           bool                     # 1ソース以上欠落 = True
```

### 2.5 SourceAllocation (配分情報)

```
SourceAllocation:
  source:         str        # "aave" | "wallet" | "cex"
  total_usd:      Decimal
  allocation_pct: Decimal    # source_usd / grand_total * 100 (grand_total=0時は 0)
  available:      bool
```

### 2.6 HF無限大処理

既存の `_cap_hf_inf()` 思想 (`backend/app/portfolio/schemas.py` L12-15) を踏襲:
`Decimal("inf")` または非有限値 → `Decimal("999.0")` にキャップしてシリアライズ。
`aggregation_schemas.py` 内で同名関数として実装する。

---

## 3. 既存 portfolio モジュールとの関係

### 3.1 既存モジュール (`backend/app/portfolio/`)

| ファイル | 役割 | 本タスクとの関係 |
|---|---|---|
| `models.py` | DBモデル (portfolio_snapshots テーブル) | 無改変。参照のみ |
| `schemas.py` | Aave単一ソース向けPydanticスキーマ | 無改変。`_cap_hf_inf` 思想を借用 |
| `snapshot_service.py` | Aave HF定期スナップショット保存 | 無改変 |
| `router.py` | `/api/portfolio/*` エンドポイント | 無改変 |
| `__init__.py` | パッケージ初期化 | 無改変 |

### 3.2 本タスクで追加するファイル

| ファイル | 役割 |
|---|---|
| `aggregation_schemas.py` | 3ソース横断集約用Pydanticスキーマ (新規) |
| `aggregation.py` | 純粋集約関数 (新規、実API非依存) |

### 3.3 設計の分離理由

既存 portfolio = Aave単一ソースの **履歴スナップショット** (時系列・DB書込)。
本タスク = 3ソース横断の **現在ビュー集約** (ステートレス純粋関数)。

既存 router/service/snapshot への改変は行わない。
実API呼出 endpoint の追加は HUMAN-REVIEW-REQUIRED スライス (段階実装 Step 2) で行う。

---

## 4. Frontend コンポーネント構成案 (案のみ / 実装はしない)

### 4.1 制約事項 (CLAUDE.md Frontend ルール厳守)

- 全テキスト日本語 (`frontend/public/locales/ja/common.json` への i18n キー追加必須)
- recharts 使用時は `dynamic(() => import('./UnifiedPortfolioChartRecharts'), { ssr: false })` 必須
- role 分離: admin / partner / viewer で表示項目を分ける
- Decimal → `Number()` でラップしてから `.toFixed()` を呼ぶ (API レスポンスは文字列)
- ダミーデータ禁止: データ未取得時は「データなし」表示

### 4.2 新規コンポーネント案

```
frontend/components/portfolio/
  UnifiedPortfolioCard.tsx          # 3ソース合算カード (grand_total表示)
  UnifiedPortfolioChartRecharts.tsx # 配分円グラフ (recharts / SSR:false)
  SourceStatusBadge.tsx             # available: bool を色付きバッジ表示
```

### 4.3 既存コンポーネントとの関係

- 既存 `PortfolioSnapshot` 系コンポーネント (Aave 履歴) は独立維持
- 新規 `UnifiedPortfolioCard` は admin ダッシュボード (`app/(admin)/dashboard/page.tsx`) に追加予定
- viewer には `sources_available` / `degraded` フラグを表示しない (admin限定)

---

## 5. 段階実装計画

### Step 1: 本 PR (Tier B / 自動進行可)
- [x] 本設計ドキュメント (`docs/59_unified_portfolio_dashboard_design.md`)
- [x] 集約スキーマ (`backend/app/portfolio/aggregation_schemas.py`)
- [x] 純粋集約関数 (`backend/app/portfolio/aggregation.py`)
- [x] pytest (`backend/tests/test_portfolio_aggregation.py`)
- 既存ファイル無改変 / 実API非依存 / frontend未着手

### Step 2: HUMAN-REVIEW-REQUIRED (実API集約エンドポイント)
- `GET /api/portfolio/unified` エンドポイント新設
- 3ソースの実API呼出 (Aave client / wallet fetch / exchange.get_status())
- `backend/app/portfolio/router.py` 拡張
- `backend/app/main.py` 配線確認 (portfolio_router は L74/L279 に既登録)
- 適切な RBAC (admin/partner 向け)

### Step 3: HUMAN-REVIEW-REQUIRED (Frontend 実装)
- `UnifiedPortfolioCard.tsx` / `UnifiedPortfolioChartRecharts.tsx` 実装
- i18n キー追加 (`frontend/public/locales/ja/common.json`)
- admin ダッシュボードへの組み込み
- E2E テスト追加

---

## 6. 【要確認】未解決事項

以下は設計段階で確認が必要な事項。Step 2/3 着手前に人間確認が必要。

| 番号 | 項目 | 詳細 |
|---|---|---|
| Q1 | Privy専用残高endpoint | wallet_balance_service には `fetch()` 関数あり (L212)。`/api/partner/wallet-balance` ルートが既存か確認必要 |
| Q2 | Bybit balance breakdown | `balance_usdt` (USDT残高) のみで十分か、他通貨 (BTC/ETH) も集約するか |
| Q3 | ユーザー単位集約 | 統合ビューは per-partner 按分か admin-level 全体ビューか |
| Q4 | 複数wallet集約 | 将来的に複数walletアドレスを集約するか (現在は1ユーザー1wallet前提) |
| Q5 | CEX残高のrole分離 | CEX残高 (Bybit) を viewer に表示するか admin 限定にするか |
| Q6 | チェーン前提の差 | Aave = Base mainnet / Base Sepolia (env切替) / Wallet = Base mainnet 固定。staging環境では wallet がBase mainnetを見るため実額と乖離する可能性あり |

### Q6 チェーン前提差 詳細

| ソース | 本番チェーン | staging チェーン | 備考 |
|---|---|---|---|
| Aave | Base mainnet | Base Sepolia (`AAVE_NETWORK=base_sepolia`) | env切替 |
| Privy Wallet | Base mainnet | Base mainnet (固定) | staging でも実残高を見る |
| Bybit CEX | 本番API | staging でも本番APIを見る | Bybit staging 環境なし |

staging では Aave だけ testnet、Wallet/CEX は mainnet の値を返すため、
統合ビューの `grand_total` が staging で混在する。Step 2 でこの差異を明示するエラーハンドリングが必要。

---

## 7. セキュリティ考慮事項

- Health Factor < 1.6 の場合は HARD_STOP (CLAUDE.md Security Rule 2)。集約関数はHFをそのまま透過するのみで安全装置の判断はしない
- `grand_total_usd` は表示用途のみ。自動取引判断の入力には使用しない
- Decimal シリアライズ: API レスポンスは文字列で返す (`field_serializer` 使用)
- 認証情報 (Bybit API key 等) は aggregation.py には一切持ち込まない
