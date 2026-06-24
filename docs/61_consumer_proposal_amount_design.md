# 設計提案: v4 非カストディアル消費者の提案金額解決

> 2026-06-25 / status: **提案 (要アーキテクト判断)** / 関連: `backend/app/automation/ai_judgment_scheduler.py:_resolve_proposal_amount`

## 背景 / 問題

liff-chat の AI 提案フロー(表示→承認→Privy 自己署名→submit-tx)は配線・RBAC とも揃っているが、**提案金額の決まり方が v4 消費者に未対応**で、消費者には提案が一切生成されない。

`_resolve_proposal_amount(db, user_id)` は `fund_allocations`(パートナー→テスターのカストディアル枠)の active 合計 × `PROPOSAL_AMOUNT_RATIO(=0.10)` を金額とする。active 行が無いと `Decimal("0")` を返し提案をスキップ(Slack 警告のみ)。

```
fund_allocations(tester_user_id=U, status='active') が無い
  → 提案金額 $0 → _create_proposals_for_users で skip → 消費者に提案が出ない
```

liff-chat 消費者(role=VIEWER・自己オンボーディング)に `fund_allocations` を登録する経路はコード上存在しない。`fund_allocations` は「パートナーが手動 INSERT」前提の custodial 概念であり、**非カストディアル消費者(自分の wallet で運用)には意味的に合わない**。

## 選択肢

### 案A: 消費者にも fund_allocations を登録(運用のみ・コード変更なし)
- onboarding 完了時 or 入金検知時に `fund_allocations` 行を INSERT する ops/バッチ。
- 長所: コード変更最小。既存ロジックそのまま。
- 短所: 非カストディアル消費者に custodial テーブルを流用する設計負債。金額が実 wallet 残高と乖離(枠を別管理)。スケールで手運用 or 別バッチが必要。

### 案B: wallet 残高ベースの金額解決(推奨・要実装)
- 消費者(fund_allocation 不在)は **本人 wallet の USDC 残高 × ratio** を提案金額にする。
- 既存資産: `backend/app/partner/wallet_balance_service.py::fetch(wallet_address)` が on-chain USDC/ETH 残高を取得(60s cache・RPC 失敗時 0 フォールバック)。
- `User.smart_wallet_address` / `User.wallet_address` で対象アドレス取得可。
- 長所: 非カストディアルの実態に一致。手運用不要。残高 0 なら自然に $0 skip(安全側)。
- 実装上の論点(要設計):
  1. **async/sync 橋渡し**: `_resolve_proposal_amount` / `_create_proposals_for_users` は sync。`wallet_balance_service.fetch` は async。ループ内で `asyncio.run` は非効率 → 事前に対象 wallet を集めて一括 await、もしくは同期版 RPC ヘルパーを用意。
  2. **チェーン分離**: `wallet_balance_service` は Base **mainnet** 固定(USDC コントラクト・Chainlink)。staging-v4 は Base **Sepolia**。env で token/feed/RPC を環境別に解決する必要(`AAVE_NETWORK` 連動)。
  3. **min/max・ratio**: 既存 `_PROPOSAL_AMOUNT_MIN_USD(50)` / `_MAX(2000)` / `_RATIO(0.10)` を踏襲。残高 < min のとき提案を出すか skip するか要決定(初期は skip 安全側)。
  4. **fail 時挙動**: RPC 失敗 = 残高 0 = skip(誤った大口提案を出さない安全側)。
  5. **Decimal 厳守**(CLAUDE.md 金融計算ルール)。

### 案C: ハイブリッド
- `fund_allocation` があればそれを優先(既存パートナー/テスター互換)、無ければ wallet 残高(消費者)。
- 案B の実装に「fund_allocation 優先 → fallback wallet 残高」の分岐を足すだけ。**後方互換を保ちつつ消費者対応**。**実質これが最有力**。

## 推奨

**案C(fund_allocation 優先 + wallet 残高 fallback)** を、案B の実装論点(async/sync・チェーン分離・fail-safe）を解いた上で実装する。金融計算の経路変更のため Plan モード + Codex/defi-review ゲート + 単体テスト(残高あり/0/RPC失敗/min境界)必須。

## 本セッションで実施済(別 PR)
- `/api/proposals/pending` 500 修正(proposals.protocol カラム追加・staging-v4)＋ alembic baseline 確立。
- `ProposalResponse` に `protocol` 露出(マルチプロトコル バッジ/注記の有効化)。
- liff-chat の silent fetch catch を可視化(PostHog `liff_data_fetch_error` + console.warn)。
- 実機 E2E: テスト proposal INSERT → liff-chat で ProposalActionCard 表示確認。
