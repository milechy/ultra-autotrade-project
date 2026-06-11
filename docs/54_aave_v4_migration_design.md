# 54_aave_v4_migration_design.md
# Aave V4 移行設計書 (EPIC-7 7-1)

作成日: 2026-06-11
Asana: EPIC-7 7-1 (Aave V4 移行設計)
ブランチ: docs/aave-v4-migration-design
関連: docs/41_kms_vault_design.md / docs/52_decision_layer_4axis_consensus_design.md / docs/34_phase2_protocols_guide.md
関連教訓: `CLAUDE.md` ドリフトカタログ「web3 API drift」「factory が constructor 引数を供給せず属性未配線 (#500)」「孤立コード」

> **Status: DRAFT (Phase 0 / 設計のみ)**。本ドキュメントは設計の正本であり、実装は別 PR (7-2 以降) で行う。
> **V4 本番アドレスは現状 Base 上に存在しない (§2 参照)。本書は「アドレス未確定状態でできる準備」と「確定後の手順」を分離して記述する。**

---

## 0. Summary

Ultra AutoTrade は現在 Aave **V3** の `Pool` コントラクト 1 本 (`getUserAccountData` / `supply` / `withdraw` / `getReserveData`) に
密結合している (`backend/app/aave/client.py`, `chains.py`)。Aave V4 は **Hub & Spoke** アーキテクチャに再構成され、
ユーザー/インテグレータは単一 `Pool` ではなく **Spoke コントラクト**経由で supply/borrow を行う (§2)。
このため V4 対応は単なるアドレス差し替えでは済まず、**ABI 差分吸収レイヤー**と**呼び出し対象コントラクトの抽象化**が必要になる。

本書は以下を設計する:

1. `AAVE_PROTOCOL_VERSION` env フラグ (`"v3"` | `"v4"`、既定 `"v3"`) による版切替方針 (7-2)
2. `chains.py` への V4 アドレス (Hub / Spoke) 登録方式 (7-3)
3. `Web3AaveClient` の V3/V4 ABI 差分吸収レイヤー設計 (7-4) — 既存 `BaseProtocolClient` (OCP) との整合
4. アドレス未確定下での準備手順 / 確定後の段階移行 / rollback (env フラグで即時 V3 復帰)
5. リスク一覧 (HF 計算互換性 / 流動性移行タイミング / web3.py 対応)

---

## 1. 現状把握 (実コード grep / 行番号付き)

### 1.1 V3 Pool ABI に密結合している箇所 — `backend/app/aave/client.py`

| 行 | 内容 | V4 影響 |
|---|---|---|
| L46-118 | `_POOL_ABI_MINIMAL` 定義 (`getUserAccountData` / `supply` / `withdraw` / `getReserveData`) | **V4 で再定義必須**。Spoke ABI は未公開 (§2.4) |
| L50-61 | `getUserAccountData(user)` → `(totalCollateralBase, totalDebtBase, availableBorrowsBase, currentLiquidationThreshold, ltv, healthFactor)` | V4 で HF 取得 API の所在 (Hub or Spoke or DataProvider) が UNVERIFIED |
| L62-73 | `supply(asset, amount, onBehalfOf, referralCode)` | V4 では Spoke 経由。引数順・referralCode 有無が UNVERIFIED |
| L74-84 | `withdraw(asset, amount, to)` → `uint256` | 同上 |
| L85-117 | `getReserveData(asset)` → 大型 tuple (aToken/variableDebtToken 等) | V4 で構造変更の可能性大 (Hub 会計) |
| L537-540 | `self._pool = self._w3.eth.contract(address=..., abi=_POOL_ABI_MINIMAL)` — 単一 Pool コントラクトオブジェクト生成 | **抽象化が必要な中核**。V4 は単一 Pool ではない |
| L600-683 | `get_health_factor()` / `get_account_data()` が `self._pool.functions.getUserAccountData(...).call()` (L617, L668) を直呼び | HF 計算経路。§5.1 互換性リスクの核心 |
| L702-913 | `deposit()` (approve → `self._pool.functions.supply(...)` L853 → revoke) — サーバー署名フロー | V4 で supply 対象が Spoke に変わる |
| L931-1085 | `withdraw()` (`self._pool.functions.withdraw(...)` L1060) | 同上 |
| L1091-1153 | `build_deposit_txs()` — 非署名 (partner 自己署名) `encode_abi("supply", ...)` (L1133) | **encode_abi は web3.py v7 API** (L1130-1131 コメント)。V4 ABI で再生成 |
| L1155-1200 | `build_withdraw_tx()` — `encode_abi("withdraw", ...)` (L1188) | 同上 |
| L356-465 | `DummyAaveClient` (staging guard / read-only) | V4 版でも dummy 互換維持が必要 |

### 1.2 チェーン / アドレス構成 — `backend/app/aave/chains.py`

| 行 | 内容 | V4 影響 |
|---|---|---|
| L21-40 | `@dataclass(frozen=True) AaveChainConfig` — `pool_address` 単一フィールド前提 | **V4 は Hub + 複数 Spoke。単一 `pool_address` では表現できない (§3 で拡張案)** |
| L45-145 | `CHAIN_REGISTRY` — `arbitrum / optimism / base / ethereum / arbitrum_sepolia / base_sepolia` の各 V3 Pool アドレスを登録 | 本番は `base` (L72-98, `pool_address=0xA238...d1c5`) |
| L72-98 | `base` チェーン: V3 Pool + 上場 15 銘柄トークンマップ | V4 Base 未デプロイ (§2.3) のため当面 V3 のまま |
| L148-160 | `get_chain_config(name)` | 版意識なし。§3.2 で `version` 軸を追加 |
| L163-178 | `get_active_chains()` — `AAVE_ACTIVE_CHAINS` env (既定 `"base"`) | V4 切替時もこの env 経路を維持 |

### 1.3 client.py 内 ハードコード V3 Pool アドレス (chains.py と二重定義)

| 行 | 定数 | 備考 |
|---|---|---|
| L152-154 | `_POOL_ADDRESS_SEPOLIA` | 出典コメント: `docs.aave.com/.../v3-testnet-addresses` |
| L159-160 | `_POOL_ADDRESS_ARBITRUM` | V3 |
| L165-166 | `_POOL_ADDRESS_ARBITRUM_SEPOLIA` | V3 |
| L171-172 | `_POOL_ADDRESS_BASE_MAINNET` | コメントに「chains.py registry の base.pool_address と一致」と明記 = **既に二重管理** |
| L174-175 | `_POOL_ADDRESS_BASE_SEPOLIA` | 同上 |

> **ドリフト注意 (既存)**: client.py の `_POOL_ADDRESS_*` 定数群と `chains.py` の `pool_address` が二重定義されている。
> V4 対応で新アドレスを足す際、**この二重管理を増やさない** (§3.2: chains.py を単一の真実源とし、client.py 定数は段階的に削減)。

### 1.4 クライアント生成経路 (factory)

| 行 | 内容 | V4 影響 |
|---|---|---|
| `client.py` L244-311 | `AaveClientBase(ABC)` — `get_health_factor` / `deposit` / `withdraw` / `build_deposit_txs` / `build_withdraw_tx` の抽象境界 | **版抽象の差し込み点**。V4 実装はこの ABC を満たせば既存呼出側を変更不要 |
| `client.py` L323-355 | `class AaveClient(Protocol)` — duck-typing 用 Protocol | 版差を内部に閉じればこの Protocol は不変 |
| `client.py` L467-516 | `Web3AaveClient.__init__` — `pool_address` 単一引数前提、`settings` 経路と `chain_name` 経路の2系統 | §4 で V4 構築引数 (hub/spoke) を追加 |
| `client.py` L581-595 | `token_addresses` 配線 (#500 教訓: factory が引数を供給しないと "Unknown asset") | **V4 でも Spoke アドレス供給漏れが #500 と同型の孤立バグになる (§5.4)** |
| `client.py` L1274-1310+ | `make_aave_client(client_type, rpc_url, pool_address, network, flashbots_rpc_url, chain_name)` ファクトリ | **版分岐の主入口**。§3.1 でここに `version` を通す |

### 1.5 OCP 基底 — `backend/app/protocols/base.py`

`BaseProtocolClient(ABC)` (L46-) が `get_protocol_name` / `get_supported_assets` / `get_current_apy` /
`supply` / `withdraw` / `get_position` / `get_health_metrics` を抽象化。Lido / Pendle / risk が継承。
**Aave クライアント (`AaveClientBase`) は現状この `BaseProtocolClient` とは別系統**である点に注意 (Aave は独自 ABC)。
V4 対応は `AaveClientBase` 側で吸収し、`BaseProtocolClient` 階層には影響させない (§3.3)。

---

## 2. Aave V4 公知情報 (出典 URL 付き / UNVERIFIED 明示)

> **本節は「設計の信頼性の核心」。確認できない項目は推測せず UNVERIFIED と明示する。**

### 2.1 アーキテクチャ — Hub & Spoke (VERIFIED)

- V4 は **Liquidity Hub & Spoke** モデル。Hub がネットワーク全体の流動性と会計を集約し、Spoke がモジュール化された借入・隔離リスクを実装する。
- **ユーザー/インテグレータは Hub を直接呼ばず、Spoke を入口として supply/borrow する**。供給資産は Hub に格納されるが、操作は常に Spoke 経由。
  出典: <https://aave.com/blog/understanding-aave-v4s-architecture>
- V4 は Ethereum mainnet 上で **3 つの Hub (Core / Prime / Plus)** を launch。各 Hub が複数の専用 Spoke に与信をルーティング。
  出典: <https://aave.com/blog/aave-v4-live-ethereum> / <https://aave.com/blog/understanding-aave-v4s-architecture>

### 2.2 リリース状況 (VERIFIED)

- **Aave V4 は 2026-03-30 に Ethereum mainnet で launch** (EthCC Cannes で発表)。
  出典: <https://thedefiant.io/news/defi/aave-v4-launches-on-ethereum-mainnet> / 検索結果 (The Block, news.bitcoin.com)
- リポジトリ `aave/aave-v4` は active (最新リリース v0.5.11 / 2026-03-20、Foundry、BUSL ライセンス、監査 3 本 = Blackthorn / TrailOfBits / ChainSecurity, 2026-02)。
  出典: <https://github.com/aave/aave-v4>

### 2.3 対応チェーン — Base 状況 (一部 VERIFIED / 一部 UNVERIFIED)

- launch 時点で **V4 が live なのは Ethereum mainnet のみ**。他チェーン拡張は Aave DAO ガバナンス承認待ち (Avalanche が検討中との報道)。
  出典: <https://aave.com/blog/aave-v4-live-ethereum> / 検索結果 (crypto.news ロードマップ)
- **【UNVERIFIED】Base mainnet への V4 デプロイ時期・有無** — 公式アドレス帳 (<https://aave.com/docs/resources/addresses>) に
  Base の V4 エントリは確認できず。「V3 が live な主要ネットワークに順次展開」という報道はあるが Base 個別の時期は**未確定**。
  → **本番 (Base) の V4 切替は、Base 上 V4 アドレスが Aave 公式アドレス帳に掲載されるまで着手不可。**

### 2.4 V3 との ABI 差分 (UNVERIFIED — 設計上の最重要未確定点)

- V3 の `Pool` 表面 (`supply` / `borrow` / `repay` / `withdraw` / `liquidationCall`) は **V4 で Hub/Spoke に分割された別表面にマップされる**。
  スマートコントラクトレベルでインテグレートする者はインタラクションコードの書き換えが必要、という方向性は VERIFIED。
  出典: <https://eco.com/support/en/articles/14800886-aave-v3-vs-v4-what-changed-and-why-it-matters>
- **【UNVERIFIED】Spoke の supply/withdraw の正確な関数シグネチャ・引数順 (referralCode / onBehalfOf 相当の有無)** —
  公式 docs (<https://aave.com/docs/aave-v4>) / GitHub README には関数シグネチャの記載なし。「supply assets / withdraw assets / user positions」という機能カテゴリのみ。
- **【UNVERIFIED】V4 の Health Factor / account data 取得 API の所在** (Hub か Spoke か専用 DataProvider か) と返却 tuple 構造。
  V3 の `getUserAccountData` 相当が V4 でどのコントラクトのどの関数になるか公式記載が確認できず。
- **【UNVERIFIED】aToken / debtToken の取り扱い** — 「depositors が aToken を受け取る」記述はあるが (出典: 検索結果 eco.com)、
  V4 の `getReserveData` 相当の構造は未確認。
- **【UNVERIFIED】Base 上 V4 の Hub/Spoke コントラクトアドレス** (§2.3 と同根。Base 未デプロイのため当然未確定)。
- **【UNVERIFIED】web3.py が V4 ABI / Spoke コントラクトを問題なく扱えるか** — ABI ベースの汎用呼出なので原理的には可能だが、
  V4 が新しい Solidity 機能 (custom errors の多用等) を使う場合の revert デコード挙動は実機検証必須 (§5.3)。

> **設計判断**: §2.4 の UNVERIFIED 群が解消するまで、本書の §3-§4 は「抽象化の器」を作るところまでを scope とし、
> **V4 の具体 ABI 文字列を実装に焼き込まない**。器だけ先に整え、シグネチャ確定後に ABI を流し込む二段構えにする (§4.3)。

---

## 3. 移行設計

### 3.1 `AAVE_PROTOCOL_VERSION` フラグ (7-2)

| 項目 | 設計 |
|---|---|
| env 名 | `AAVE_PROTOCOL_VERSION` |
| 値 | `"v3"` (既定) \| `"v4"` |
| 解決箇所 | `make_aave_client()` (client.py L1274) 内で `os.getenv("AAVE_PROTOCOL_VERSION", "v3")` を読む |
| 既定挙動 | env 未設定 = `"v3"` = **現行と完全に同一挙動** (no-op で安全) |
| 不正値 | `"v3"`/`"v4"` 以外は **起動時 fail-fast** (`AaveClientError`)。silent fallback 禁止 (drift 防止) |
| staging/prod 分離 | `.env.staging` / `.env.production` で独立設定 (CLAUDE.md 環境分離ルール準拠)。クロスコンタミ禁止 |

分岐方針 (OCP):

```text
make_aave_client(...)
  └─ version = getenv("AAVE_PROTOCOL_VERSION", "v3")
       ├─ "v3" → Web3AaveClientV3  (= 現 Web3AaveClient、改名 or alias)
       └─ "v4" → Web3AaveClientV4  (新規、AaveClientBase を継承)
```

両者とも `AaveClientBase` (ABC) を満たすため、**呼出側 (service.py / rebalance_service.py 等) は一切変更不要**。
これが「env フラグで即時 V3 復帰」(§4.5 rollback) を成立させる核心。

### 3.2 `chains.py` への V4 アドレス登録 (7-3)

V4 は単一 `pool_address` で表せないため、`AaveChainConfig` (L21-40) に **version 軸を追加**する。
**既存フィールドは破壊せず追加のみ** (後方互換 = `"v3"` 利用時に挙動不変):

```python
@dataclass(frozen=True)
class AaveV4Config:
    """V4 Hub/Spoke アドレス。値は Aave 公式アドレス帳掲載後に確定 (それまで None)。"""
    hubs: dict[str, str]          # {"core": "0x...", "prime": "0x...", "plus": "0x..."}
    spokes: dict[str, str]        # {"main": "0x...", ...} — supply/withdraw の実呼出先
    data_provider_address: str | None = None  # HF/account data 取得先 (UNVERIFIED)

@dataclass(frozen=True)
class AaveChainConfig:
    ...  # 既存フィールドは不変 (pool_address は V3 用として残す)
    v4: Optional["AaveV4Config"] = None   # V4 未対応チェーンは None
```

- **chains.py を V4 アドレスの唯一の真実源**とし、client.py L152-175 の `_POOL_ADDRESS_*` 二重定義を**これ以上増やさない**
  (§1.3 ドリフト注意)。V4 アドレスは client.py には書かない。
- Base の `v4` は **Base 上 V4 デプロイ確認まで `None`** (§2.3)。`None` のまま `AAVE_PROTOCOL_VERSION=v4` を指定したら
  `make_aave_client` で fail-fast (「base に V4 設定なし」)。

### 3.3 ABI 差分吸収レイヤー (7-4)

`Web3AaveClientV4` を `AaveClientBase` 継承で新規作成し、**V3/V4 差は client 内部に閉じる**。

| 抽象メソッド (AaveClientBase) | V3 実装 | V4 実装 (UNVERIFIED ABI のため器のみ) |
|---|---|---|
| `get_health_factor()` | `self._pool.functions.getUserAccountData(user)` (L617) | V4 HF 取得 API (DataProvider/Hub/Spoke のいずれか — §2.4) を呼ぶ adapter |
| `get_account_data()` | 同 `getUserAccountData` (L668) | 同上 |
| `deposit()` (署名) | `self._pool.functions.supply(...)` (L853) | **Spoke** `.functions.<supply相当>(...)` |
| `withdraw()` (署名) | `self._pool.functions.withdraw(...)` (L1060) | **Spoke** `.functions.<withdraw相当>(...)` |
| `build_deposit_txs()` (非署名) | `self._pool.encode_abi("supply", ...)` (L1133) | Spoke contract の `encode_abi(<supply相当>, ...)` |
| `build_withdraw_tx()` (非署名) | `self._pool.encode_abi("withdraw", ...)` (L1188) | Spoke contract の `encode_abi(<withdraw相当>, ...)` |

設計上の不変条件:

1. **戻り値の型・単位を V3 と完全一致させる** (HF は `Decimal`、金額は wei→Decimal 変換済み)。
   呼出側 (HF < 1.6 → HARD_STOP 等の安全装置) を V4 が静かに壊さないため。
2. **`encode_abi` は web3.py v7 API を踏襲** (L1130-1131, L1187 のコメント通り)。
   `encodeABI` (camelCase / 旧 API) を V4 実装で復活させない (ドリフトカタログ「web3 API drift」)。
3. **V4 ABI 文字列は §2.4 確定まで定数として焼き込まない**。`_SPOKE_ABI_MINIMAL` 等は確定後 PR で追加 (§4.3)。

### 3.4 OCP 整合 (BaseProtocolClient との関係)

- V4 対応は `AaveClientBase` (Aave 独自 ABC) 内に閉じる。`protocols/base.py` の `BaseProtocolClient` 階層 (Lido/Pendle/risk) には**波及させない**。
- `make_aave_client` の version 分岐のみが拡張点 = **拡張に開・変更に閉** (OCP)。既存 V3 クラスのロジックは触らない (改名/alias のみ)。

---

## 4. 移行手順とフェーズ分割

### 4.1 Phase 0 — アドレス未確定下でできる準備 (7-2 / 7-3 の器部分のみ / 本書 scope)

DoD: 全て `AAVE_PROTOCOL_VERSION` 未設定 (=v3) で**挙動不変**であること (回帰ゼロ)。

1. `AAVE_PROTOCOL_VERSION` 読取 + fail-fast バリデーションを `make_aave_client` に追加 (既定 v3)
2. `AaveV4Config` dataclass を `chains.py` に追加 (値は全チェーン `None`)
3. `Web3AaveClientV4` の**空殻**を `AaveClientBase` 継承で追加 — 各メソッドは `NotImplementedError("Aave V4 ABI 未確定")` を投げる
4. `make_aave_client` の `"v4"` 分岐で `Web3AaveClientV4` を返す経路を配線 (が、アドレス `None` のため実利用は fail-fast)
5. unit test: `AAVE_PROTOCOL_VERSION=v3` で全既存テスト pass / `=v4` で `NotImplementedError` を確認 / 不正値で fail-fast
6. **孤立コード検出 (Gate 5) 必須**: `Web3AaveClientV4` が make_aave_client から到達可能か (#500 同型の未配線防止)

### 4.2 Phase 1 — Base 上 V4 アドレス確定後 (§2.3 解消が前提)

1. Aave 公式アドレス帳から Base の Hub/Spoke アドレスを取得し `chains.py` の `base.v4` に登録 (出典 URL をコメントに記載)
2. §2.4 の UNVERIFIED 群 (関数シグネチャ / HF API / reserve 構造) を**実機 Base mainnet read-only call で確認** (write しない)
3. 確定した ABI を `_SPOKE_ABI_MINIMAL` 等として追加 (§4.3)

### 4.3 Phase 2 — V4 実装 (ABI 焼き込み + adapter 実装)

1. `Web3AaveClientV4` の `get_health_factor` / `get_account_data` を read-only 実装 → **staging (Base Sepolia 上 V4 があれば) で HF 一致検証**
2. `deposit` / `withdraw` / `build_*_txs` を Spoke 経由で実装
3. **V3 と V4 で同一ウォレットの HF が一致することを実機照合** (§5.1)
4. Gate 1-7 全通過 + `/defi-aave-review` skill 必須 (HF / Decimal / approve+supply 変更のため)

### 4.4 Phase 3 — staging 検証 → 本番切替

1. staging (`.env.staging`) で `AAVE_PROTOCOL_VERSION=v4`、Shadow Mode 観測
2. 本番 (`.env.production`) は `AAVE_PROTOCOL_VERSION=v3` のまま据置 → staging soak 合格後に切替
3. 切替は env 1 行変更 + コンテナ再起動 (deploy_production.sh)。コード再デプロイ不要

### 4.5 Rollback (env フラグで即時 V3 復帰)

| トリガ | 操作 | 所要 |
|---|---|---|
| V4 で HF 異常 / supply 失敗 / 流動性不足 | `.env.production` の `AAVE_PROTOCOL_VERSION=v4` → `v3` に戻す + コンテナ再起動 | 数分 |
| コード再デプロイ | **不要** (V3 クラスは常に同梱、§3.1) | — |

> **rollback が成立する前提**: V3 実装を V4 移行後も**削除しない** (両実装を常時同梱)。
> V4 安定確認後に V3 を削除するのは別 EPIC とし、本移行では消さない。

---

## 5. リスク一覧

| # | リスク | 内容 | 対策 |
|---|---|---|---|
| R1 | **HF 計算の互換性** | V4 の HF 取得 API・単位・しきい値解釈が V3 と異なると、`HF < 1.6 → HARD_STOP` 等の安全装置が誤発火/不発火 | §3.3 不変条件1 (戻り値型・単位を V3 一致)。Phase 2 で同一ウォレット HF 実機照合 (§4.3-3)。`/defi-aave-review` 必須 |
| R2 | **流動性移行タイミング** | V3→V4 への TVL 移行途上は Base の V4 流動性が薄く、supply/withdraw が想定 APY/スリッページにならない | 本番切替を staging soak 合格 + V4 Base TVL しきい値確認後に限定 (§4.4)。env rollback 即応 (§4.5) |
| R3 | **web3.py V4 対応** | V4 が custom error を多用する場合、web3.py の revert デコードが V3 と異なり例外メッセージが変質 → ログ/握りつぶし箇所が劣化 | Phase 1 で実機 read-only 検証 (§4.2-2)。`encodeABI`(旧 camelCase) を復活させない (ドリフトカタログ「web3 API drift」)。`# type: ignore[attr-defined]` を安易に付けない |
| R4 | **アドレス二重管理ドリフト** | client.py `_POOL_ADDRESS_*` (§1.3) と chains.py の二重定義に V4 アドレスを足すと乖離 | V4 アドレスは chains.py のみ (§3.2)。client.py に V4 定数を書かない |
| R5 | **孤立コード (#500 同型)** | `Web3AaveClientV4` が factory から到達不能 / Spoke アドレス未配線で "Unknown asset" 相当 | Phase 0 DoD に Gate 5 孤立コード検出必須 (§4.1-6)。token/spoke アドレス供給を factory で検証 |
| R6 | **環境分離違反** | staging で v4、prod で v3 のはずが env クロスコンタミで本番が誤って v4 化 | `.env.staging` / `.env.production` 独立設定。`scripts/check_env_separation.sh` でガード |
| R7 | **UNVERIFIED 前提の実装焼き込み** | §2.4 未確定 ABI を推測で実装 → 本番 revert | 器のみ Phase 0 (§4.1)。具体 ABI は確定後 Phase 2 (§4.3)。`NotImplementedError` で未確定を明示 |

---

## 6. Definition of Done (本設計の後続実装 PR 用)

各 Phase の PR は以下を満たすこと:

- [ ] **Phase 0**: `AAVE_PROTOCOL_VERSION` 未設定で全既存 pytest pass (回帰ゼロ) / 不正値 fail-fast / Gate 5 孤立コード検出 pass
- [ ] **Phase 1**: Base V4 アドレスの出典 URL を chains.py コメントに明記 / §2.4 UNVERIFIED の実機 read-only 検証ログ添付
- [ ] **Phase 2**: 同一ウォレット HF が V3/V4 で一致する実機照合出力 / `/defi-aave-review` skill 通過 / Decimal 型維持
- [ ] **Phase 3**: staging soak 合格証跡 / 本番切替は env 1 行 + 再起動のみ (コード再デプロイなし) / rollback 手順検証済
- [ ] **全 Phase 共通**: Gate 1-3 (verify.sh) / web3 API drift grep (`encodeABI`/`buildTransaction`/`rawTransaction` 残存ゼロ) / 環境分離 check

---

## 7. 出典一覧

| # | URL | 内容 |
|---|---|---|
| 1 | <https://aave.com/blog/understanding-aave-v4s-architecture> | Hub & Spoke / Spoke 経由 supply/borrow |
| 2 | <https://aave.com/docs/aave-v4> | V4 公式 docs (関数シグネチャ記載なし) |
| 3 | <https://aave.com/blog/aave-v4-live-ethereum> | Ethereum mainnet launch / Core/Prime/Plus Hub / Base 言及なし |
| 4 | <https://thedefiant.io/news/defi/aave-v4-launches-on-ethereum-mainnet> | 2026-03-30 launch |
| 5 | <https://github.com/aave/aave-v4> | repo active / v0.5.11 / BUSL / 監査3本 / 関数シグネチャ README に記載なし |
| 6 | <https://eco.com/support/en/articles/14800886-aave-v3-vs-v4-what-changed-and-why-it-matters> | V3 Pool 表面 → V4 Hub/Spoke 分割 / aToken 受領 / 書換え必要 |
| 7 | <https://aave.com/docs/resources/addresses> | 公式アドレス帳 (Ethereum に Hub/Spoke、Base の V4 エントリ確認できず) |
