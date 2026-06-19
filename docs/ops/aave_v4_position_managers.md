# Aave V4 Position Managers — 調査と UATa 適合度評価

> 作成日: 2026-06-19 / Asana GID: 1215620579110282
> 種別: 調査ドキュメント（コード変更なし）
> 出典: Aave V4 公式ドキュメント（WebFetch 取得、末尾参照） / `backend/app/aave/client.py`（現行 V3 実装、読むのみ）
>
> **本書の API・仕様は推測ではなく Aave V4 公式ドキュメント（`aave.com/docs/aave-v4/positions/managers` 等）の WebFetch 取得結果に基づく（2026-06-19 時点）。**
> ⚠️ Aave V4 は 2026-03-30 に **Ethereum Mainnet のみ**でローンチ。**Base には未展開**（`docs/ops/aave_v4_migration_plan.md` 参照）。本書は Base 展開時に即着手するための事前調査。

---

## 概要

Aave V4 の **Position Managers** は、ユーザーが明示的に承認した**スマートコントラクトがユーザーのポジションを代理操作**できる仕組み。
公式定義: *"Position managers are smart contracts users can authorize to manage their positions, enabling automated actions like supplying, withdrawing, borrowing, and repaying — while maintaining full user control."*

つまり「supply / withdraw / borrow / repay をユーザーに代わって自動実行できる権限付きコントラクト」であり、想定ユースケースは
**自動戦略・vault プロトコル・リスク管理・アカウント抽象化（AA）**。これは UATa の「AI による自動 rebalance を、
ユーザーの秘密鍵を預からずに実行したい」という非カストディアル要件と概念的に強く重なる（適合度は後述）。

V4 の Position Managers は **Spoke 単位**で管理される（Spoke = V4 の借入モジュール。V3 の Pool に相当。`migration_plan.md` 参照）。

---

## Position Managers API 仕様

> 公式ドキュメントは TypeScript SDK（React hooks）レベルの API を提示している。
> オンチェーンの低レベル method（manager コントラクトが実装すべき interface / Spoke 側の認可 storage）は
> 本ページ範囲では完全には開示されておらず、Base 展開時に address-book / コントラクト ABI で要再確認（後述「実装時の注意点」）。

### 認可フロー（有効化 / 無効化）

```typescript
// position manager の有効化・無効化
const [setPositionManager, { loading, error }] = useSetSpokeUserPositionManager(
  (transaction) => sendTransaction(transaction)
);

await setPositionManager({
  spoke: SpokeId,        // どの Spoke のポジションを対象にするか
  manager: EvmAddress,   // 代理管理させる manager コントラクトのアドレス
  approve: boolean,      // true=有効化 / false=無効化（取消）
  user: EvmAddress       // ポジション所有者
});
```

### 探索（discovery）hooks

| hook | 役割 |
|---|---|
| `useSpokePositionManagers(request)` | その Spoke で利用可能な全 manager を取得 |
| `useSpokeUserPositionManagers({ spoke, user })` | あるユーザーが有効化済みの manager を取得 |

### 組み込み（built-in）managers

全 Spoke に自動で存在する 2 つ:

| manager | 役割 | アドレス取得 |
|---|---|---|
| `NativeTokenGateway` | ネイティブトークン（ETH）ラップ対応 | `spoke.chain.nativeGateway` |
| `SignatureGateway` | ERC-20 Permit（署名承認）対応 | `spoke.chain.signatureGateway` |

### 認可モデル（重要）

| 性質 | 内容 | UATa への含意 |
|---|---|---|
| **明示承認必須** | manager はユーザーが enable しない限り一切操作できない | 非カストディアル原則と整合（◎） |
| **いつでも取消可能** | *"Users can disable a manager at any time to revoke its access"* | 緊急停止経路を作りやすい（◎） |
| **ガバナンス登録が前提** | *"Position managers are registered with a spoke through governance before users can enable them"* | UATa 独自 manager を使うには **Aave DAO ガバナンス登録が必要**（△ 重大制約） |
| **権限粒度は binary・spoke-wide** | per-action（supply のみ / borrow のみ）の scope は**存在しない**。enable すると当該 Spoke のポジション全体を操作可能 | 最小権限原則に反する（▲ 要リスク評価） |
| **時間制限・spend cap なし** | per-tx 承認・上限額・有効期限の仕組みは公式記載なし | UATa 側 application-layer での上限制御が必須（▲） |

---

## V3 onBehalfOf 方式との比較

UATa 現行（V3）は `backend/app/aave/client.py` で **Pool の `onBehalfOf` 引数**を使う:

```python
# 現行 V3: supply の第3引数 onBehalfOf にユーザーwallet を渡す
self._pool.functions.supply(asset, amount_wei, checksum_wallet, 0)  # checksum_wallet = onBehalfOf
# build_deposit_txs / build_withdraw_tx も同様に「ユーザー本人が署名して送る」非カストディアル設計
```

| 観点 | V3 `onBehalfOf` 方式（現行 UATa） | V4 Position Managers |
|---|---|---|
| 権限の持続性 | **都度指定**。tx ごとに onBehalfOf を渡す。永続的な代理権限ではない | **永続登録**。一度 enable すれば取消まで有効 |
| 誰が tx を送るか | UATa は未署名 tx を build → **ユーザー本人（Privy）が署名・送信**（`build_deposit_txs`） | enable 後は **manager コントラクトが自律的に**送信可能 |
| supply の代理 | `supply(..., onBehalfOf=user)` は誰でも他人に供給可能（資産は user の aToken へ） | manager が user のポジションへ supply |
| borrow / withdraw の代理 | V3 では他人の代わりに borrow するには **credit delegation（`approveDelegation`）** が別途必要。withdraw は本人のみ | enable 済み manager は borrow / withdraw / repay も代理可能（spoke-wide） |
| 鍵管理 | UATa はサーバー鍵を持たない（build-tx パターン）。ユーザー署名必須 | manager コントラクト自体は鍵不要（コントラクトが executor）。ただし誰が manager を駆動するかは別設計 |
| 自動化の容易さ | 自動 rebalance のたびにユーザー署名が要る（UX 摩擦） | **enable 一度で以降自動化可能**（UX 大幅改善） |
| 取消 | 都度なので「取消」概念が薄い（次回 build しなければ良い） | `approve=false` で明示取消。緊急停止と親和 |

**要点**: V4 Position Managers は「毎回ユーザー署名」の UX 摩擦を解消し、UATa の自動 rebalance を**真に自動化**できる。
一方で「永続権限・spoke-wide・ガバナンス登録必須」という新たな制約とリスク面を持ち込む。

---

## UATa での活用シナリオ

### シナリオ A: UATa rebalance manager（本命・要ガバナンス登録）
UATa が「rebalance 専用 manager コントラクト」を実装し、Aave DAO に登録 → ユーザーが LIFF/PWA から enable。
以降、AI Optimizer の判断で UATa が **ユーザー署名なしに自動 rebalance**（supply/withdraw 切替）を実行。

- 利点: UX 摩擦ゼロ、真の自動運用。秘密鍵は依然 UATa が持たない（非カストディアル維持）。
- 制約: (1) Aave DAO ガバナンス登録（数週間〜数ヶ月、不確実）、(2) manager コントラクトの監査が必須、
  (3) spoke-wide 権限のため manager コントラクト側で「rebalance 以外は実行しない」ロジックを**自前で固める**必要。

### シナリオ B: 組み込み manager のみ利用（低リスク・短期）
`SignatureGateway`（Permit）を使い、approve tx を署名レスにして **build_deposit_txs の 2 tx を 1 tx 化**。
ガバナンス登録不要（built-in）。自動化はしないが UX 改善。移行第一歩として現実的。

### シナリオ C: 当面は onBehalfOf 継続（V4 でも supply の onBehalfOf は superset 維持の公算）
V4 は *"a superset of V3, preserving all prior functionality"*。Position Managers を**使わず**、現行の
build-tx + ユーザー署名方式を V4 Spoke 向けに ABI 差し替えるだけで移行。最小コスト・最小リスク。

> **推奨初期方針**: **C（最小移行）→ B（Permit で UX 改善）→ A（自動化、ガバナンス登録が取れれば）** の段階導入。
> A は「非カストディアルのまま完全自動化」という UATa の理想だが、ガバナンス登録の不確実性と spoke-wide 権限の
> セキュリティ評価が前提。Base 展開後に別 EPIC として評価する。

---

## 実装時の注意点

1. **オンチェーン低レベル ABI は未確定**: 公式は SDK(hooks)中心。manager コントラクトが実装すべき interface と
   Spoke の認可 method（enable/disable の実 calldata）は、Base 展開時に
   [aave/address-book](https://github.com/bgd-labs/aave-address-book) と Spoke ABI で**実 grep 確認**（鉄則9）。推測で書かない。
2. **権限粒度なし = application-layer で守る**: enable すると spoke-wide。UATa manager は内部で
   「単一取引上限 10% / 日次 30% / HF<1.6 HARD_STOP」（`CLAUDE.md §Security Rules`）を**コントラクト or backend 両方で**強制する。
3. **緊急停止との配線**: `approve=false`（disable）を UATa 緊急停止フラグ（OR ロジック・上書き不可）と連動させる経路を設計する。
4. **ガバナンス登録は外部依存リスク**: シナリオ A はローンチクリティカルパスに置かない。B/C を主経路とする。
5. **監査必須**: 代理実行コントラクトは資金移動権限を持つ。外部監査なしに本番投入しない（`defi-security-audit` スキル参照）。
6. **非カストディアル原則の不変性**: いずれのシナリオでも UATa はユーザー秘密鍵を保持しない。これは `project_staging_noncustodial_proof_state` の検証済み前提を崩さない。

---

## 出典（WebFetch / WebSearch、2026-06-19）

- [Position Managers | Aave V4 Docs](https://aave.com/docs/aave-v4/positions/managers) — 概念・SDK API・認可フロー・built-in managers・セキュリティ
- [Spokes | Aave V4 Docs](https://aave.com/docs/aave-v4/liquidity/spokes) — Spoke = borrowing module・data 構造
- [Aave V4 Launch Explained | Bitcoin.com](https://news.bitcoin.com/aave-v4-launch-explained-hub-and-spoke-model-new-partners-and-what-changes-for-borrowers/) — V4 は V3 の superset・Ethereum mainnet 2026-03-30・他チェーンは DAO 審議中
- 内部参照: `backend/app/aave/client.py`（V3 `onBehalfOf` / build-tx 非カストディアル実装）/ `docs/ops/aave_v4_migration_plan.md`
