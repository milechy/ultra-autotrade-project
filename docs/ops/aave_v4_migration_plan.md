# Aave V3 → V4 移行計画（UATa 観点）

> 作成日: 2026-06-19 / Asana GID: 1215620579110282
> 種別: 設計ドキュメント（コード変更なし）
> 出典: Aave V4 公式ドキュメント・一次報道（WebFetch、末尾参照）/ `backend/app/aave/client.py` / `backend/app/aave/chains.py`（読むのみ）
>
> **目的: Aave V4 が Base に展開された時点で即着手できる状態を作る。**
> **本書の数値・差分は推測ではなく公式ドキュメントと現行実装の実 grep に基づく（2026-06-19 時点）。**

---

## Aave V4 Hub-and-Spoke 概要

Aave V4 は 2026-03-30 に **Ethereum Mainnet のみ**でローンチした新アーキテクチャ。
*"V4 is a superset of V3, preserving all prior functionality while enabling a more modular design."*（V3 機能を内包しつつモジュール化）

| 構成要素 | 役割 | V3 での対応 |
|---|---|---|
| **Liquidity Hub** | 流動性を集約保持するコンテナ。`id / name / chain / address`、`totalSupplied / totalBorrowed`、`totalSupplyCap / totalBorrowCap` を持つ | （V3 には無い概念。V3 は各市場が独立 Pool） |
| **Spoke** | 個別の借入モジュール（isolated borrowing module）。独自の collateral ルール・リスクパラメータ・`liquidationConfig` を持ち、`connectedHubs` で Hub に接続。`id / name / address / chain / liquidationConfig / summary / connectedHubs` | **V3 の Pool コントラクトに相当（ユーザーの supply/withdraw/borrow の窓口）** |
| **Risk Premiums** | ポジションのリスクに応じて借入コストを変動させる仕組み（後述） | V3 は原則一律レート + eMode |
| **GHO** | V4 のネイティブ settlement asset | V3 でも GHO は存在 |

要するに **「1 Hub（流動性プール）に複数 Spoke（借入市場）がぶら下がる」** 構造。UATa から見た最大の差分は
**「Pool アドレス 1 個 → Hub + Spoke の複数アドレス体系」** に変わること。

### Risk Premiums が HF 計算に与える影響

公式・解説記事より（数値は出典に基づく）:

- **3 階層**のリスクプレミアム。基盤は **Asset Liquidity Premium**: 各資産に **0%（最高品質）〜 1000%（最も高リスク）** のリスクスコア。
- **Collateral Risk Premium**: リスクの高い担保を使うと、base debt accumulation に対して**追加のプレミアム債務**が上乗せされる。
  例: GHO base rate 5%・担保ミックスが 30% premium → 借入は base debt accrual の +30% 分が追加で積み上がる。
  WETH 等の高品質担保は 0% premium。
- **Health Factor の式自体は V3 と同じ**: `HF = eligible collateral value / debt value`、**1 を割ると清算**。
- ただし **premium debt が上乗せされる分、債務が速く増える → HF の減衰が V3 より速くなりうる**（特に低品質担保）。
- **清算ロジックは変更**: 固定 close factor を廃止し、清算者は **Spoke 単位で設定された Target Health Factor** まで回復する分だけ返済（over-liquidation 防止）。liquidation bonus は HF に応じて変動。

> **UATa への含意**: `HF < 1.6 → HARD_STOP`（`CLAUDE.md §Security Rules 2`）の閾値自体は V4 でも有効（HF 意味論が保存されるため）。
> ただし (1) リスクプレミアムで HF 減衰が速まる担保があるため**監視 cadence / バッファの再検討**が必要、
> (2) Spoke の **Target Health Factor** を読み取り、UATa の 1.6 と整合するか確認、
> (3) UATa の取扱い銘柄ごとの Asset Liquidity Premium を把握し、高 premium 銘柄は保守化する余地。

---

## Base 展開状況・確認方法

| 項目 | 状態（2026-06-19） |
|---|---|
| V4 ローンチ | ✅ Ethereum Mainnet（2026-03-30） |
| Base 展開 | ❌ **未展開** |
| 他チェーン拡大 | DAO ガバナンス審議中。Avalanche が評価対象。**Base の確定タイムライン・AIP は未確認** |

→ **現時点で UATa の本番（Base Mainnet）は V3 を継続。V4 移行は Base 展開待ち。**
本書「Base V4 展開確認コマンド」を定期実行し、展開検知後に実装フェーズを起票する（「次フェーズ起票案」参照）。

---

## V3→V4 差分（UATa 観点）

### 1. Pool コントラクトアドレスの変化
- V3: チェーンごとに **Pool アドレス 1 個**（例: Base `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`）。
- V4: **Hub アドレス + Spoke アドレス（市場ごと）** の体系へ。ユーザー操作は **Spoke** が窓口（V3 Pool の置換）。
  → `chains.py` の `pool_address: str` 単一フィールドでは表現できない。`hub_address` + `spoke_address`（または資産→Spoke マップ）が必要。

### 2. ABI の変化
- 現行 `client.py` の `_POOL_ABI_MINIMAL` は **V3 Pool ABI**（`getUserAccountData / supply / withdraw / getReserveData / setUserEMode / getUserEMode`）。
- V4 では Spoke の ABI に差し替え。`getUserAccountData` 相当の **unified accounting** API、`supply/withdraw` のシグネチャ、
  eMode の扱い（Risk Premiums により再設計の可能性）を **Base 展開時に実 ABI で確認必須**（推測で ABI を書かない／鉄則9）。

### 3. eMode → Risk Premiums
- V3 の eMode（`setUserEMode / getUserEMode`、UATa は `emode_optimizer.py` で活用）は、V4 では Risk Premiums 体系に統合・再設計される公算。
  `build_set_emode_tx` / `get_user_emode` が V4 でそのまま使えるか要検証。

---

## 変更が必要なファイルと関数一覧

> ⚠️ **パス訂正（鉄則9 / ドリフトカタログ）**: Asana タスクおよび参照は `backend/app/aave/web3_aave_client.py` を指すが、
> **実ファイルは存在しない**。現行実装は **`backend/app/aave/client.py`**（クラス `Web3AaveClient` / `DummyAaveClient` / `AaveClientBase` / Protocol `AaveClient`）。
> 実装着手時は `client.py` を対象とすること。

### `backend/app/aave/client.py`（変更対象の関数）

| 関数 / 箇所 | 現行（V3） | V4 で必要な変更 |
|---|---|---|
| `_POOL_ABI_MINIMAL`（定数） | V3 Pool ABI | V4 Spoke ABI へ差し替え（新規定数 `_SPOKE_ABI_MINIMAL` 追加が安全） |
| `_POOL_ADDRESS_BASE_MAINNET`（定数） | `0xA238...d1c5` | V4 Base Spoke アドレスへ（展開後に確定） |
| `Web3AaveClient.__init__` | `pool_address` を受けて `self._pool` を構築 | `spoke_address`（+必要なら `hub_address`）を受ける。V3/V4 両対応の分岐 or バージョンフラグ |
| `get_health_factor` | `getUserAccountData(user)[5]` | V4 unified accounting の HF 取得 API へ。HF スケール（1e18）が同一か確認 |
| `get_account_data` | `getUserAccountData` の 6 戻り値をパース | V4 の口座データ構造に合わせて再パース。liquidation_threshold / Target HF の扱い |
| `deposit`（supply） | `Pool.supply(asset, amount, onBehalfOf, refCode)` | `Spoke.supply(...)` へ。シグネチャ差分・refCode 有無を確認 |
| `withdraw` | `Pool.withdraw(asset, amount, to)` + HF<1.6 ガード | `Spoke.withdraw(...)` へ。HF<1.6 ガードは維持 |
| `build_deposit_txs` | `encode_abi("supply"/"approve")` | Spoke ABI に対する `encode_abi`。非カストディアル build-tx は維持 |
| `build_withdraw_tx`（同ファイル後半） | `encode_abi("withdraw")` | 同上 |
| `get_user_emode` / `build_set_emode_tx` | `setUserEMode / getUserEMode` | V4 で eMode が Risk Premiums に統合される場合は再設計 or 廃止 |
| `get_pool_utilization`（`monitor.py` 等で `getReserveData`） | V3 `getReserveData` | V4 Hub の `totalSupplied/totalBorrowed` から算出へ |

### `backend/app/aave/chains.py`（追記内容）
- `AaveChainConfig` に **V4 フィールド追加**: `hub_address: Optional[str]`、`spoke_addresses: Optional[dict[str, str]]`（資産/市場→Spoke）、`aave_version: int = 3`（3/4 切替）。`frozen=True` は維持。
- `CHAIN_REGISTRY` に **Base V4 エントリ追加**（展開後にアドレス確定）。当面は V3 `base` を残し、`base_v4` として並存 → 切替期に安全に移行。
- 既存 `base` の `tokens`（15 銘柄）は V4 Spoke の上場銘柄に合わせて見直し（V4 で銘柄が異なる可能性）。

### その他影響を受けうるモジュール（要追跡）
`emode_optimizer.py`（eMode→Risk Premium）/ `monitor.py`・`reserve_monitor.py`（getReserveData→Hub）/
`liquidation_sentinel.py`・`safety_score.py`（Target HF・清算ロジック変更）/ `rebalance_*`（Spoke 単位の rebalance）。

---

## 移行コスト見積もり

> 工数は dev VPS での実装 + Base Sepolia V4 検証前提の粗見積もり。Base V4 の実 ABI 確定後に再算定。

| 作業項目 | 工数（人日） | リスク | 備考 |
|---|---|---|---|
| `chains.py` V4 レジストリ拡張（フィールド + Base V4 エントリ） | 0.5〜1 | 低（Tier S: 単一ファイルだが registry 構造変更） | 後方互換維持（v3/v4 並存） |
| `client.py` Spoke ABI 差し替え + supply/withdraw 配線 | 3〜5 | **高**（資金移動経路・Tier S 相当の安全系） | 実 ABI 確認必須・Plan モード必須 |
| `get_health_factor` / `get_account_data` の V4 対応 | 1〜2 | 高（HARD_STOP 判定の根幹） | HF スケール・unified accounting 確認 |
| Risk Premium を踏まえた HF 監視 cadence 見直し | 1〜2 | 中 | `liquidation_sentinel` / `safety_score` 連動 |
| eMode → Risk Premium 移行（`emode_optimizer`） | 2〜3 | 中 | V4 仕様確定次第 |
| Position Managers 評価/PoC（任意・別 EPIC） | 5〜10 | 高（ガバナンス登録・監査） | `aave_v4_position_managers.md` シナリオ A |
| Base Sepolia V4 での E2E 検証（build-tx→sign→supply→HF） | 2〜3 | 中 | `project_staging_noncustodial_proof_state` の手順を V4 で再走 |
| **合計（Position Managers 除く最小移行）** | **約 8〜16 人日** | — | Spoke ABI 確定が前提 |

**主要リスク**: (1) Base V4 展開タイミングが不確実（DAO 依存）、(2) Spoke ABI / unified accounting の実仕様が
ドキュメントだけでは確定できず実コントラクト確認が要る、(3) 資金移動経路 = Tier S 相当のため Opus + Plan モード + Codex adversarial review 必須。

---

## Base V4 展開確認コマンド

> Base に V4 が展開されたら以下で検知 → 即着手。`AAVE_RPC_URL_BASE` は既存 env を流用。

```bash
# 1) Aave 公式 address-book に Base V4 が載ったか（最も確実な一次ソース）
#    bgd-labs/aave-address-book に AaveV4Base 系の export が出たら展開済みのサイン
curl -s https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/ts/AaveV4Ethereum.ts | head -5
#    Base 版が存在するか（404 なら未展開）
curl -s -o /dev/null -w "%{http_code}\n" \
  https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/ts/AaveV4Base.ts

# 2) ガバナンスで Base V4 有効化 AIP が出ているか
#    governance.aave.com / vote.onaave.com を "V4 Base activation" で確認（手動 or WebFetch）

# 3) Spoke/Hub アドレスが判明したら、Base 上に実コントラクトが存在するか cast で確認
#    （foundry cast。"0x" 以外が返ればコントラクト存在）
cast code <SPOKE_ADDRESS> --rpc-url "$AAVE_RPC_URL_BASE" | head -c 12; echo

# 4) Spoke の getUserAccountData 相当が呼べるか（read-only 疎通。ABI 確定後）
cast call <SPOKE_ADDRESS> "getUserAccountData(address)" <TEST_WALLET> --rpc-url "$AAVE_RPC_URL_BASE"

# 5) 現行 V3 Pool がまだ生きているか（移行期の並存確認）
cast code 0xA238Dd80C259a72e81d7e4664a9801593F98d1c5 --rpc-url "$AAVE_RPC_URL_BASE" | head -c 12; echo
```

確認後の即着手チェック:
- [ ] address-book に Base V4 アドレス（Hub / Spoke）が確定
- [ ] Spoke ABI を取得し `supply / withdraw / getUserAccountData 相当` のシグネチャを実 grep 確認（鉄則9）
- [ ] HF スケール（1e18 か）を `cast call` 実値で確認
- [ ] Base Sepolia に V4 testnet があれば先にそこで検証

---

## 次フェーズ（実装）の起票案

Base V4 展開検知後、以下を Asana に起票（Phase 計画 5 軸確認のうえ）:

1. **[Tier S / Opus / Plan] V4 Spoke 対応 — `client.py` ABI 差し替え + supply/withdraw 配線**
   触るファイル: `backend/app/aave/client.py`。DoD: Base Sepolia V4 で build-tx→sign→supply→HF 取得を実走。Codex adversarial review 必須。
2. **[Tier S] `chains.py` V4 レジストリ拡張（hub/spoke/version フィールド + Base V4 エントリ）**
   触るファイル: `backend/app/aave/chains.py`。v3/v4 並存で後方互換維持。
3. **[Tier B] HF 監視 cadence 見直し（Risk Premium 反映）**
   触るファイル: `liquidation_sentinel.py` / `safety_score.py` / `reserve_monitor.py`（別ファイルなら並列可）。
4. **[Tier B / 別 EPIC] Position Managers PoC 評価**（`aave_v4_position_managers.md` シナリオ A/B）。ガバナンス登録の不確実性ありローンチクリティカルパス外。
5. **[Tier B] Base Sepolia V4 E2E 検証スクリプト**（非カストディアル lifecycle の V4 再走）。

各タスクは「触るファイル」を実パスで宣言し、着手前に `grep -rn "def supply\|def withdraw\|getUserAccountData" backend/app/aave/client.py` で現状確認（鉄則9）。

---

## 出典（WebFetch / WebSearch、2026-06-19）

- [Aave V4 Overview / Hubs | Aave Docs](https://aave.com/docs/aave-v4/liquidity/hubs) — Hub の定義・caps
- [Spokes | Aave V4 Docs](https://aave.com/docs/aave-v4/liquidity/spokes) — Spoke = borrowing module・liquidationConfig
- [Position Managers | Aave V4 Docs](https://aave.com/docs/aave-v4/positions/managers) — Position Managers（→ `aave_v4_position_managers.md`）
- [Aave V4 launches on Ethereum mainnet | The Block](https://www.theblock.co/post/395617/aave-v4-launches-ethereum-mainnet) / [Bitcoin.com](https://news.bitcoin.com/aave-v4-launch-explained-hub-and-spoke-model-new-partners-and-what-changes-for-borrowers/) — 2026-03-30 Ethereum-only・他チェーン DAO 審議中
- [Aave V4 Risk Premiums | Aave Blog](https://aave.com/blog/aave-v4-risk-premiums) / [V4 Liquidations | Aave Blog](https://aave.com/blog/aave-v4-liquidations) — Asset Liquidity Premium 0–1000%・Target Health Factor・variable bonus
- 内部参照: `backend/app/aave/client.py`（V3 実装・ABI・関数）/ `backend/app/aave/chains.py`（CHAIN_REGISTRY）/ `CLAUDE.md §Security Rules`
