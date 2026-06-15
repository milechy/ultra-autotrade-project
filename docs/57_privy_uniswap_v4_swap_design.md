# 57 Privy + Uniswap V4 スワップ統合 設計ドキュメント

> 作成: 2026-06-15  
> スコープ: Phase 1 scaffold (型定義・純粋バリデータ)  
> ブランチ: `feat/privy-uniswap-v4-swap-design`  
> 関連 PR: 本ブランチ参照

---

## 1. 現状の取引経路マップ

Ultra AutoTrade が現在統合している取引経路を以下に示す。
Uniswap 本実装は **不在**（本スライスが初回 scaffold）。

| プロトコル | 経路 | 実装状態 |
|---|---|---|
| **Aave V3** | Polygon / Arbitrum — supply / borrow / repay / withdraw | `backend/app/aave/` 実装済み |
| **Bybit (ccxt)** | spot 取引 / 板情報 | `backend/app/exchange/` 実装済み |
| **OKX (ccxt)** | spot バックアップ | `backend/app/exchange/` 実装済み |
| **DCA** | Bybit 定期積立 | `backend/app/dca/` 実装済み |
| **Pendle RouterV4** | YT/PT swap / add_liquidity (hosted SDK calldata) | `backend/app/protocols/pendle/` 実装済み |
| **Lido** | ETH staking / stETH 取得 | `backend/app/protocols/lido/` 実装済み |
| **Uniswap V4** | ERC-20 汎用スワップ | **本スライス: Phase 1 scaffold のみ** |

---

## 2. Pendle RouterV4 hosted-SDK パターンの参照

Pendle RouterV4 実装（`backend/app/protocols/pendle/client.py`）は以下のパターンを確立している。
Uniswap V4 統合も同型の段階設計が妥当と判断する。

### Pendle パターン（参照実装）

| 側面 | Pendle RouterV4 の実装 |
|---|---|
| calldata 生成 | Pendle hosted SDK (`/sdk/api/v1`) — 外部 HTTP。ローカル ABI encode 不要 |
| デフォルト実行モード | `dry_run=True`（シミュレーションのみ）。`False` は明示指定が必要 |
| 宛先照合 | SDK レスポンスの `tx.to` と既知 Router アドレスを照合（C2 検証） |
| 秘密鍵 | router.py / main.py 配線 (Tier S) まで触れない |
| スリッページ | `RouterV4SwapRequest.slippage`（0 < x <= 0.05）+ `min_amount_out` 二層防御 |
| 10%上限 | `amount_in_usd / portfolio_value_usd` 両指定時のみ検証。片方欠落は fail-closed |

### Uniswap V4 への適用方針

Pendle と同様に段階設計（Phase 1→4）を採用する（詳細は §6「段階実装計画」参照）。
`dry_run=True` をデフォルトとし、SDK calldata 取得・署名・broadcast は
HUMAN-REVIEW-REQUIRED として段階的に実装する。

---

## 3. Uniswap V4 アーキテクチャ概要

### V4 の主要変更点（V3 との差分）

| 項目 | Uniswap V3 | Uniswap V4 |
|---|---|---|
| Pool 管理 | 各 Pool が独立コントラクト | **PoolManager 単一コントラクト**（全 pool を集約） |
| Pool Key | address で識別 | `PoolKey`（token0/1 + fee + tickSpacing + hooks） |
| Hooks | なし | **hooks**: 独自ロジックを Pool ライフサイクルに注入可能 |
| ルーター | SwapRouter02 | **Universal Router**（V2/V3/V4 を統合） |
| ガス | Pool ごとにトークン転送 | flash accounting で一括決済（ガス削減） |

### Privy 署名経路

Privy による署名検証は `backend/app/auth/privy_verifier.py` に実装済み。
ウォレット秘密鍵は Privy Embedded Wallet 側で管理し、
バックエンドは秘密鍵を保持しない設計（Security Rules §1 準拠）。

Uniswap V4 の tx 署名 Phase 3 では、以下の経路を想定する:
1. フロントエンドが Privy SDK を通じて署名リクエストを送信
2. バックエンドは calldata + to アドレスを返却（秘密鍵は扱わない）
3. フロントエンドが Privy Embedded Wallet で署名 + broadcast

---

## 4. 【要確認】5 項目（推測確定禁止）

**以下は Phase 2 着手前に実機確認・公式ドキュメント照合が必要な未確定事項。**
推測で実装を進めないこと（CLAUDE.md 鉄則 9）。

### C1. calldata 生成方式

| 候補 | 概要 | 要確認点 |
|---|---|---|
| **Uniswap hosted quoting API** | `https://api.uniswap.org/v2/quote` 等 — Pendle 同型 | レート制限・認証要否・V4 対応状況 |
| **ローカル ABI encode** | web3.py で Universal Router calldata を生成 | V4 の `Commands` + `inputs` バイト列の仕様 |
| **Uniswap SDK (TypeScript)** | Python backend から subprocess/HTTP で呼び出す | デプロイアーキテクチャ・レイテンシ |

**推奨確認先**: Uniswap Developer Docs (https://docs.uniswap.org) / GitHub `Uniswap/v4-core` / `Uniswap/universal-router`

### C2. SDK 言語とバックエンド連携方式

Uniswap 公式 SDK は TypeScript (`@uniswap/v4-sdk`)。
Python backend から呼び出す場合の方式を確認:

- HTTP microservice（Node.js wrapper）経由
- subprocess 呼び出し（レイテンシ・エラーハンドリング考慮必要）
- Python 非公式 SDK の採用可否（Pendle 同様 hosted API のみ使用する代替）

### C3. Universal Router 正式アドレス（chain 別）

| Chain | PoolManager アドレス | Universal Router アドレス |
|---|---|---|
| Ethereum Mainnet | **【要確認】** | **【要確認】** |
| Arbitrum | **【要確認】** | **【要確認】** |
| Base | **【要確認】** | **【要確認】** |
| Optimism | **【要確認】** | **【要確認】** |
| Polygon | **【要確認】** | **【要確認】** |

**推奨確認先**: `https://docs.uniswap.org/contracts/v4/deployments`
Phase 2 着手前にアドレスを確定し、`backend/app/protocols/uniswap/config.py`（新規）にクラス定数として定義すること。

### C4. PoolKey / hooks パラメータ表現

V4 スワップには `PoolKey` 構造体が必要:
```
struct PoolKey {
    Currency currency0;
    Currency currency1;
    uint24 fee;
    int24 tickSpacing;
    IHooks hooks;
}
```
hooks なし（デフォルト）の場合の `IHooks` アドレス（`address(0)` か別の定数か）を確認。

### C5. Privy 署名 broadcast 経路

Phase 3 で実装する署名経路の詳細:
- Privy Embedded Wallet でフロントエンドが直接 broadcast するか
- バックエンドが RPC 経由で broadcast するか（秘密鍵不要な場合のみ許容）
- `eth_sendRawTransaction` の RPC エンドポイント（chain 別）

---

## 5. スリッページ保護設計（二層防御）

```
Layer 1: リクエスト内 slippage（0 < slippage <= 0.05）
         UniswapV4SwapIntent.slippage フィールドで制約
         validators.compute_min_amount_out() で min_amount_out 計算

Layer 2: SlippageGuard 再利用（backend/app/aave/slippage_guard.py）
         操作前後の価格変動監視（Phase 3 以降で適用）
         is_stablecoin() でステーブルコイン判定を再利用
```

**実装方針**:
- `slippage_guard.py` を **import 再利用**（本体改変なし）
- `is_stablecoin()` はシンボル文字列（"USDC" 等）を引数とする
  → アドレス形式の場合は False 扱い（Phase 1 では補足情報のみ）

---

## 6. 段階実装計画

### Phase 1: 型定義・純粋バリデータ（本スライス / Tier B 自動進行）

| ファイル | 内容 |
|---|---|
| `backend/app/protocols/uniswap/schemas.py` | `UniswapV4SwapIntent` / `UniswapV4SwapEstimate` |
| `backend/app/protocols/uniswap/validators.py` | 純粋関数バリデータ（I/O なし） |
| `backend/tests/protocols/test_uniswap/` | pytest ユニットテスト |
| `docs/57_privy_uniswap_v4_swap_design.md` | 本ドキュメント |

DoD: ruff / mypy / pytest 全通過。安全境界グリーン（web3/秘密鍵/calldata なし）。

### Phase 2: SDK calldata 取得（HUMAN-REVIEW-REQUIRED）

前提: C1/C3/C4 未確定事項の確認完了後に着手。

| ファイル | 内容 |
|---|---|
| `backend/app/protocols/uniswap/client.py`（新規） | quoting API 呼び出し。`dry_run=True` 前提 |
| `backend/app/protocols/uniswap/config.py`（新規） | chain 別 Router アドレス定数 |

制約: 秘密鍵不使用。calldata 取得のみ（broadcast なし）。

### Phase 3: 署名 + broadcast（HUMAN-REVIEW-REQUIRED）

前提: Phase 2 完了 + C5（Privy 経路）確認完了。

- Privy Embedded Wallet 連携（フロントエンド主体、バックエンドは calldata 提供のみ）
- tx 送信後の receipt / event log 確認ロジック

### Phase 4: main.py ルーター配線（Tier S / シリアル実装）

前提: Phase 3 ステージング検証完了 + セキュリティレビュー通過。

- `backend/app/main.py`（Tier S）へのルーター登録
- RBAC（admin / partner ロール別アクセス制御）
- Rate Limit・Cooldown（Aave 同等基準）

---

## 7. 単一取引10%上限の実装方針

Security Rules §3「Max single trade: 10% of total assets」に基づく。

```python
# validators.validate_swap_intent() 内の実装
if has_amount_usd != has_portfolio_usd:
    # 片方のみ: 検証不能 → fail-closed 拒否
    errors.append("fail-closed: 片方のみ指定では10%上限を検証できない")
elif has_amount_usd and has_portfolio_usd:
    if amount_in_usd > portfolio_value_usd * Decimal("0.10"):
        errors.append("単一取引上限超過: 10% を超えている")
# 両方 None: USD 評価不能のためスキップ（ネイティブ量のみの場合）
```

両方 None の場合（ネイティブ量 `amount_in` のみ指定）はチェックをスキップする。
Phase 2 以降で quoting API から USD 換算を取得し、`amount_in_usd` に設定することを推奨。

---

## 8. 安全境界（Phase 1 の保証）

以下を grep で実証（セルフ DoD の一部）:

```bash
# 実行系/秘密鍵/calldata が含まれないこと
grep -rniI "private_key|web3|eth_account|broadcast|requests\.|httpx|calldata|sign_transaction" \
  backend/app/protocols/uniswap/ || echo "安全境界OK"

# float 使用禁止
grep -rn "float" backend/app/protocols/uniswap/ || echo "float不使用OK"

# main.py 未配線
grep -nE "uniswap" backend/app/main.py || echo "main.py未配線OK"

# slippage_guard.py 無改変
git diff -- backend/app/aave/slippage_guard.py | head -1 || echo "slippage_guard無改変OK"
```

---

## 9. 参照

| ドキュメント / ファイル | 用途 |
|---|---|
| `backend/app/protocols/pendle/schemas.py` | RouterV4SwapRequest の Decimal/field_validator パターン |
| `backend/app/protocols/pendle/client.py` | hosted SDK calldata 取得パターン |
| `backend/app/aave/slippage_guard.py` | SlippageGuard 再利用（import のみ） |
| `backend/app/auth/privy_verifier.py` | Privy 署名検証（Phase 3 参照） |
| `docs/13_security_design.md` | Security Rules 全文 |
| `docs/34_phase2_protocols_guide.md` | Pendle RouterV4 SDK 設計詳細 |
| `CLAUDE.md § Security Rules` | float 禁止 / Decimal 必須 / 秘密鍵 env のみ |
