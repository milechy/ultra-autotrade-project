# Privy Policy Engine 設計ドキュメント

**バージョン**: 1.0.0-scaffold
**作成日**: 2026-06-15
**対象ブランチ**: docs/privy-policy-engine-design
**ステータス**: Phase 1 (scaffold) 実装済み — Phase 2-4 は HUMAN-REVIEW-REQUIRED

---

## 目次

1. [統合方針](#1-統合方針)
2. [既存安全装置との二重化マップ](#2-既存安全装置との二重化マップ)
3. [重大所見: 既存 PolicyEngine 未配線](#3-重大所見-既存-policyengine-未配線)
4. [ポリシー定義スキーマ案](#4-ポリシー定義スキーマ案)
5. [段階実装計画](#5-段階実装計画)
6. [要確認事項](#6-要確認事項)

---

## 1. 統合方針

### 1.1 二層構造の整理

Ultra AutoTrade のポリシー制御は **異なる保証境界を持つ 2 層**で構成する。
これらは補完関係であり、片方で代替できるものではない。

```
┌─────────────────────────────────────────────────────────────┐
│  Privy signer-layer policy (Privy サーバーサイド)           │
│  ・allowlist: 宛先コントラクト / 資産 の静的許可リスト      │
│  ・spending limit: 期間内送金上限 (静的リテラル)            │
│  ・conditional sign: 条件付き署名 (静的値のみ)              │
│  ・保証: 秘密鍵に到達する前の最終防衛線                     │
│  ・制約: 動的自己参照 (onBehalfOf == msg.sender) は未サポート│
└──────────────────────────┬──────────────────────────────────┘
                           │ 補完関係 (代替不可)
┌──────────────────────────▼──────────────────────────────────┐
│  application-layer PolicyEngine (backend/app/policy/)        │
│  ・engine.py: hard rule (HF floor / velocity cap / cooldown) │
│  ・wallet_policy.py: 宣言的ポリシースキーマ (本スライス)    │
│  ・保証: DB 参照・複合条件・動的ユーザー属性を扱える        │
│  ・制約: 秘密鍵に触れない; calldata 再検証は aave/client.py │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 配置方針

Privy server-side policy の宣言的スキーマ (`WalletPolicySpec`) を
`backend/app/policy/wallet_policy.py` として **既存 `engine.py` と同一パッケージに併置**する。

理由:
- `engine.py` と同一の Decimal/env 規律を踏襲できる
- 将来の `PolicyEngine.check()` 配線時に import が自然
- Privy API 呼出層 (Phase 3) は別モジュールに分離し、スキーマ層は純粋に保つ

---

## 2. 既存安全装置との二重化マップ

以下の実装位置はすべて grep 実値による確認済み情報。推測値は含まない。

| CLAUDE.md Security Rule | application-layer 実装位置 (grep 実値) | Privy server policy で表現可能か | 判定 |
|---|---|---|---|
| **HF < 1.6 → HARD_STOP** | `backend/app/automation/monitoring_service.py:193-233`<br>`AaveOperationMode.HARD_STOP` (HF < 1.6 で設定)<br>`emergency_stop` OR logic: 行 239-250 | 可能: spending limit を `0` に設定すれば実質 HARD_STOP に相当。ただし HF の動的取得は Privy 側では不可 | **補完**: Privy は静的フォールバックのみ。動的 HF 監視は application-layer 必須 |
| **単一取引 10% 上限** | `backend/app/policy/engine.py:21`<br>`_DEFAULT_MAX_POSITION_USD = Decimal("10000")`<br>Rule 3 (`amount_usd > max_position_usd`) 行 100-103 | 可能: `spending_limit.per_transaction` で静的上限を設定できる | **二重化推奨**: Privy 側で絶対上限、engine.py で動的割合計算 |
| **日次 30% 上限** | `backend/app/policy/engine.py:22`<br>`_DEFAULT_DAILY_CAP_USD = Decimal("50000")`<br>Rule 4 日次 velocity cap: 行 143-151 | 可能: `spending_limit.per_day` で設定できる (静的リテラル) | **二重化推奨**: Privy 側で絶対額上限、engine.py で DB 集計ベースの実績計算 |
| **cooldown 10 分** | `backend/app/policy/engine.py:24`<br>`_DEFAULT_COOLDOWN_SECONDS = 600`<br>Rule 6 cooldown: 行 166-181 | 不可: Privy spending limit は時間窓指定だが「前回 tx からの間隔」は非サポート | **application-layer 専任**: engine.py の `_check_cooldown()` が唯一の実装 |
| **emergency_stop OR logic** | `backend/app/automation/monitoring_service.py:239-250`<br>`backend/app/automation/workflow.py:331` (`"emergency_stop"` 返却) | 不可: Privy policy は OR 条件付き状態機械を持たない | **application-layer 専任**: 手動 stop を Privy side では上書き不能 |
| **HF floor (engine.py)** | `backend/app/policy/engine.py:25`<br>`_DEFAULT_HF_FLOOR = Decimal("1.5")`<br>Rule 7: 行 111-114 | 不可: 動的値 (期待 HF) との比較は Privy 未サポート | **application-layer 専任** |

### 補足: aave/client.py の静的リテラル制約

`backend/app/aave/client.py:1418-1424` のコメントにより、
Privy Policy Engine は `onBehalfOf == msg.sender` の動的自己参照比較を未サポート
(value は静的リテラルのみ)。本人一致検証は `build_partner_tx` エンドポイントの
calldata 再検証 (`_decode_pool_calldata`) で担保している。
Privy allowlist でこれを代替することはできない。

---

## 3. 重大所見: 既存 PolicyEngine 未配線

### 3.1 確認事実

`backend/app/policy/engine.py` には完全実装済みの `PolicyEngine.check()` が存在するが、
以下の grep 結果により **本番コードパスに配線されていない**ことを確認した。

```bash
# 実行コマンド (再現可能)
grep -rn "get_policy_engine()\|PolicyEngine()\|\.check(" backend/app/ \
  | grep -v test | grep -v "engine.py"
# 結果: backend/app/auth/router.py:249: # kyc_service.check(...) のコメント行のみ
# → PolicyEngine.check() の本番呼出はゼロ件
```

具体的に未配線の経路:

| 経路 | 現状 | 期待状態 |
|---|---|---|
| `POST /{proposal_id}/approve` (`proposals/router.py:642`) | PolicyEngine を呼ばず即 `status="approved"` | approve 前に `engine.check(ctx, db)` を呼び、blocked なら 422 返却 |
| 提案生成時 (create proposal) | 未確認 (separate grep 必要) | 同上 |

### 3.2 是正提案 (配線案)

以下は **実装提案のみ**。実際の配線は HUMAN-REVIEW-REQUIRED とする。

```python
# proposals/router.py の approve_proposal 内 (Step 1 前に挿入する案)
from app.policy.engine import PolicyContext, get_policy_engine  # noqa: PLC0415

def approve_proposal(...):
    # ...提案取得...

    # [是正案] Step 0: PolicyEngine hard rule チェック
    policy_ctx = PolicyContext(
        user_id=proposal.user_id,
        asset=proposal.asset,
        operation=proposal.operation,
        amount_usd=Decimal(str(proposal.amount_usd)),
        expected_hf_after=Decimal(str(proposal.expected_hf_after))
            if proposal.expected_hf_after else None,
        proposal_id=proposal.id,
    )
    result = get_policy_engine().check(policy_ctx, db)
    if result.blocked:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"policy_violations": result.violations},
        )

    # Step 1: 承認済みにマーク (既存コード)
    proposal.status = "approved"
    ...
```

この配線の実施判断・レビュー・テストは **Phase 2 の HUMAN-REVIEW-REQUIRED スライス**で行う。

---

## 4. ポリシー定義スキーマ案

Privy server-side policy を宣言的に表現するスキーマ。
実装は `backend/app/policy/wallet_policy.py` として本スライスで作成済み。

### 4.1 `WalletAllowlistRule`

```
宛先コントラクトアドレス / 資産シンボル の allowlist。
Privy server policy の allowlist 設定に対応。
```

| フィールド | 型 | 説明 |
|---|---|---|
| `allowed_contracts` | `frozenset[str]` | 許可コントラクトアドレス (小文字 0x...) |
| `allowed_assets` | `frozenset[str]` | 許可資産シンボル (大文字) |

バリデーション:
- `allowed_contracts` は空不可 (空の allowlist は全許可と解釈される危険があるため)
- コントラクトアドレスは `0x` prefix + 40 hex 文字
- `allowed_assets` は空不可

### 4.2 `SpendingLimitRule`

```
期間内送金上限。Privy server policy の spending_limit 設定に対応。
金融計算規則 (Rule 11): 全フィールドは Decimal 型必須。
```

| フィールド | 型 | 説明 |
|---|---|---|
| `per_transaction_usd` | `Decimal` | 単一 tx 上限 (USD) |
| `per_day_usd` | `Decimal` | 日次上限 (USD) |
| `per_week_usd` | `Optional[Decimal]` | 週次上限 (USD, 省略可) |

バリデーション:
- 全値は正値 (`> 0`)
- `per_transaction_usd <= per_day_usd` (単一 tx が日次を超えるのは矛盾)
- `per_day_usd <= per_week_usd` (指定時: 日次が週次を超えるのは矛盾)
- engine.py の定数との整合: `per_transaction_usd` は `_DEFAULT_MAX_POSITION_USD`(10000) 以下推奨

### 4.3 `ConditionalSignRule`

```
条件付き署名ルール。Privy server policy の conditional_sign 設定に対応。
注意: Privy は静的リテラル値のみ比較可能。動的自己参照は非サポート。
```

| フィールド | 型 | 説明 |
|---|---|---|
| `field_path` | `str` | チェック対象 calldata フィールドパス |
| `operator` | `Literal["eq", "neq", "gt", "lt", "gte", "lte", "in", "not_in"]` | 比較演算子 |
| `value` | `str \| list[str]` | 比較値 (静的リテラルのみ) |
| `description` | `str` | ルール説明 (監査用) |

バリデーション:
- `field_path` は空不可
- `operator` が `in` / `not_in` のとき `value` はリスト型必須
- `operator` が `eq`/`neq`/`gt`/`lt`/`gte`/`lte` のとき `value` は文字列型必須
- `value` リストは空不可

### 4.4 `WalletPolicySpec`

全ルールのコンテナ。

| フィールド | 型 | 説明 |
|---|---|---|
| `wallet_address` | `str` | 対象ウォレットアドレス (0x...) |
| `policy_id` | `str` | 識別子 (監査ログ用) |
| `allowlist` | `Optional[WalletAllowlistRule]` | allowlist ルール |
| `spending_limit` | `Optional[SpendingLimitRule]` | spending limit ルール |
| `conditional_signs` | `list[ConditionalSignRule]` | 条件付き署名ルール (0 個以上) |

バリデーション:
- `wallet_address` は 0x prefix + 40 hex 文字
- `policy_id` は空不可
- 少なくとも 1 つのルール (`allowlist` または `spending_limit` または `conditional_signs` 非空) が必要

---

## 5. 段階実装計画

### Phase 1: 純粋スキーマ + バリデータ (本スライス / Tier B / 自動進行可)

| 成果物 | ステータス |
|---|---|
| `docs/56_privy_policy_engine_design.md` (本文書) | 完了 |
| `backend/app/policy/wallet_policy.py` | 完了 |
| `backend/tests/test_wallet_policy.py` | 完了 |

**制約**: Privy API 呼出なし / 秘密鍵なし / 既存ファイル無改変

### Phase 2: 既存 PolicyEngine 配線是正 (HUMAN-REVIEW-REQUIRED)

- `proposals/router.py` の `approve_proposal` 前に `engine.check()` を配線
- 提案生成 endpoint でも同様に配線
- 回帰テスト: `tests/test_policy_engine.py` / `tests/test_proposal_wallet_propagation.py`

**理由で HUMAN-REVIEW**: 本番承認フローの変更、既存挙動への影響が大きい

### Phase 3: Privy server policy 同期層 (HUMAN-REVIEW-REQUIRED)

- `WalletPolicySpec` を Privy API に送信して server-side policy を設定するクライアント実装
- 依存追加 (`privy-sdk` または `requests`/`httpx`)
- 認証トークン管理 (env 変数)
- 本番 wallet への policy 適用

**理由で HUMAN-REVIEW**: 実資金ウォレットへの設定変更、秘密鍵環境変数追加、外部 API 呼出

### Phase 4: main.py 配線 + 起動時 policy 同期 (HUMAN-REVIEW-REQUIRED)

- startup event hook で `WalletPolicySpec` を Privy に同期する機構
- `backend/app/main.py` の startup イベントへの登録

**理由で HUMAN-REVIEW**: Tier S ファイル (`main.py`) 変更

---

## 6. 要確認事項

以下は **現時点で確定できない項目**。推測での確定禁止。Phase 3 着手前に人間が確認すること。

### 6.1 Privy server SDK

| 項目 | 現状 | 確認方法 |
|---|---|---|
| SDK 言語/パッケージ名 | 不明。公式 docs 要確認 | https://docs.privy.io/guide/server/wallets/policy-engine |
| Python SDK の有無 | 不明。REST API 直叩きが必要な可能性あり | 上記 docs |
| 認証方式 | 不明 (API key / JWT / OAuth?) | Privy dashboard → Settings → API Keys |
| policy API エンドポイント | 不明 | Privy API reference |
| policy の適用タイミング (即時 vs 非同期) | 不明 | API response schema 確認 |

### 6.2 allowlist / spending limit と aave/client.py の制約の波及

`backend/app/aave/client.py:1418-1424` の確認事項:
- Privy は静的リテラルのみ比較可能 → Aave V3 Pool コントラクトアドレスは不変なので allowlist には記載可能
- `onBehalfOf == msg.sender` の動的比較は **Privy 未サポート確定**。calldata 再検証 (`_decode_pool_calldata`) が必須であり、Privy allowlist で代替不可
- spending limit の `per_transaction_usd` 設定時、USD 換算が Privy 側でできるか不明 (token amount のみの可能性あり)

### 6.3 既存 wallet との整合

- 現在の Aave SUPPLY/WITHDRAW に使用している wallet address が Privy 管理下かどうか未確認
- `AAVE_WALLET_PRIVATE_KEY` と Privy wallet の共存方針 (non-custodial 移行ロードマップ) 未確定

### 6.4 環境分離

- staging (Base Sepolia) / production (Base Mainnet) で Privy policy を別々に管理するか
- Privy の環境 (sandbox / production) が staging 環境と一致するか

---

*このドキュメントは Phase 1 (scaffold) 完了時点の設計記録です。*
*Phase 2 以降の実装前に本文書を更新し、6節の「要確認事項」を解消すること。*
