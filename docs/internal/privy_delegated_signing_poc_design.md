# Privy Delegated Signing PoC — 設計 doc

- Status: Draft (PoC 設計)
- Owner: backend / wallet
- 関連 PR: 本 PR (skeleton + design only)
- 関連 memory: `privy_key_recovery_policy`
- 関連 doc: `docs/internal/staging_build_speedup_design.md`(参考 doc format)
- 日付: 2026-05-23

---

## 1. 目的と背景

### 1.1 現状

現在の AAVE 実行パスは **単一鍵 `AAVE_WALLET_PRIVATE_KEY`** に依存している。
全ユーザの supply / withdraw / repay は、運営側が保管する 1 本の private key で署名され、
on-chain では「運営の単一ウォレット」として実行される。

これは MVP / Phase 1 では成立する一方、以下の課題が残る:

- **ユーザ資産分離が on-chain で行えない**
  会計上は user_id 紐付けで管理しているが、on-chain では混在
- **鍵漏洩時の blast radius が全ユーザ**
- **規制対応・監査時に「ユーザ毎の自己保管」を主張できない**
- **ユーザが自分の Privy ウォレット残高で AAVE 操作を行う体験に不整合**

### 1.2 Phase 3 のゴール

Phase 3 では、**per-user delegated signing** を導入し、以下を満たす:

- 各ユーザの Privy embedded wallet が自分の資金で AAVE を操作する
- 運営(operator)はユーザから **明示的に scope を限定された delegation** を受領し、
  AI judgment による自動運用を実行する
- scope 外の操作は運営側からも一切実行できないことを保証する
- ユーザはいつでも revoke できる

### 1.3 本 PR のスコープ

本 PR は **設計 doc + クラス骨格まで**。
実 delegated 実行コード(Privy SDK 呼び出し / on-chain 署名)は **別 PR** で扱う。

---

## 2. 方式比較

Phase 3 の per-user signing を実現するため、以下 3 方式を比較した。

| 方式 | scope | 鍵管理 | UX | リスク | 採否 |
|---|---|---|---|---|---|
| Privy delegated actions | 細かい | Privy 保管 | 良 | Privy 依存 | 候補A |
| Privy session signer | 中 | Privy 保管 + session | 良 | session 期限 | 候補B |
| server-side wallet | 自由 | 自社 KMS | 中 | 鍵漏洩リスク | 不採用 |

### 2.1 Privy delegated actions(候補 A・本命)

- ユーザが「特定の action(例: AAVE supply)を最大 N USDC まで」を delegation token として発行
- 運営は token を保持し、scope 外の操作は SDK レイヤで弾かれる
- pros:
  - scope が action 単位 / 金額単位で細かく定義できる
  - Privy 側で SDK / dashboard / 監査ログがそろう
  - ユーザは「何を許可したか」を Privy UI で確認・revoke できる
- cons:
  - Privy ベンダー依存(SLA・SDK 変更リスク)
  - 各 action ごとに delegation の整備が必要(初期実装コスト)
- 採用理由:
  - scope を狭く保てる(operator が壊れても被害最小)
  - audit & ユーザ revoke のセルフサービス性が高い

### 2.2 Privy session signer(候補 B・fallback)

- 一定期間有効な session 鍵を Privy 側で発行し、operator がその session で署名
- pros:
  - 実装が比較的薄い(action ごとの細分は不要)
  - 期限切れで自動失効するため鍵漏洩 blast radius を時間で抑制
- cons:
  - session 期限内は **scope 内のあらゆる操作が可能**(action 粒度の絞り込みが緩い)
  - 期限切れの再同意が UX 上わずらわしい
- 不採用理由:
  - Phase 3 では AI 自動運用が前提なので、action 単位の制限が必要
  - 候補 A が SDK 都合で出せなくなった場合の **fallback として温存**

### 2.3 server-side wallet(不採用)

- ユーザ毎に運営側が KMS で鍵を生成・保管し、運営が直接署名
- pros: 完全に自由
- cons:
  - **「自己保管」を主張できない**(規制リスク)
  - KMS 鍵漏洩時の blast radius が全ユーザ
  - ユーザの Privy embedded wallet との二重管理になり混乱
- 不採用理由:
  - 本プロダクトの「Privy embedded wallet を user の所有として扱う」設計と不整合

---

## 3. scope 制限の設計

Privy delegated actions を採用する前提で、以下の scope を delegation token に焼き込む。

### 3.1 操作種別 (action)

最小限の 3 種に絞る。Phase 3 PoC では AAVE 経由の lend / repay のみ。

| action | 説明 | 備考 |
|---|---|---|
| `aave:supply` | USDC を AAVE pool に supply | AI judgment が「lend」を選んだ時 |
| `aave:withdraw` | aUSDC を burn して USDC を引き出す | AI judgment が「withdraw」を選んだ時 / 緊急停止 |
| `aave:repay` | 借入の repay | Phase 3 初期では未使用、scope の枠だけ確保 |

scope 外の例(明示的に **拒否** されるべき):

- ERC-20 任意 transfer(ユーザの USDC を任意の宛先に送る)
- DEX swap
- bridge
- approve(amount=MAX)
- proxy / delegatecall 系の任意呼び出し
- 別 protocol(Compound / Morpho 等)の呼び出し

### 3.2 数量上限

token に焼き込む quota:

| 上限種別 | 既定値 (PoC) | 備考 |
|---|---|---|
| per-tx 上限 (USDC) | 1000 | 1 トランザクションで動かせる最大量 |
| per-day 上限 (USDC) | 5000 | 24h ローリング累積上限 |

per-day はサーバ側カウンタでも二重に enforce する(token 側 + DB 側)。
on-chain 強制が難しい部分は、サーバが scope 外と判定して **execute_action を実行しない** で担保する。

### 3.3 有効期限

- 既定 90 日
- 90 日ごとに UI で再同意を求める(P1 Privy onboarding の中で再表示)
- 期限切れの delegation は execute_action 側で即座に拒否

### 3.4 revoke 経路

| 経路 | 主体 | 手段 |
|---|---|---|
| ユーザ revoke (UI) | user | Privy dashboard / 自社設定画面 |
| ユーザ revoke (API) | user | `POST /api/wallet/delegation/revoke` |
| operator revoke | ops | admin script から `PrivyDelegatedClient.revoke()` |
| 緊急 kill-switch | ops | `disable_ai_scheduler` ON + 全ユーザ delegation を一括 revoke スクリプト |

revoke 後の挙動:

- 進行中の tx は当然止まらない(on-chain なので)
- 新規 execute_action は即座に「delegation revoked」で 4xx
- ai_decisions には `delegation_revoked` 理由で reject を記録

---

## 4. user 同意フロー

### 4.1 同意取得のタイミング

P1 (Privy MVP) onboarding の最後に、以下の専用画面を挟む:

```
[ 自動運用に必要な権限を確認 ]

ultra-autotrade は、あなたの代わりに以下の操作のみを行います:
  ・AAVE への USDC supply
  ・AAVE からの USDC withdraw

以下の制限がかかります:
  ・1 回あたり最大 1000 USDC
  ・1 日あたり最大 5000 USDC
  ・有効期限: 90 日(以降は再同意が必要)

許可しない操作:
  ・任意の宛先への送金
  ・DEX swap や別 protocol 呼び出し
  ・上限を超える操作

いつでも「設定 > 自動運用の権限」から取消せます。

[ 同意して開始 ]   [ 後で ]
```

### 4.2 同意内容のレコーディング

`user_actions` テーブル(P0-6 で導入)に以下の event を記録:

- `delegation.granted` (scope JSON, expires_at)
- `delegation.revoked` (理由, 主体: user / operator)
- `delegation.renewed`

### 4.3 「後で」を選んだ user

- AAVE 自動運用は無効(execute_action は呼ばれない)
- それ以外の機能(残高表示・手動 supply など)は引き続き利用可能
- onboarding 完了とは扱うが、「自動運用 OFF」として表示

---

## 5. サーバ署名の境界

### 5.1 operator が動かせる範囲

| 操作 | 可 / 不可 | 理由 |
|---|---|---|
| 当該 user の `aave:supply` (scope 内) | 可 | 同意済 |
| 当該 user の `aave:withdraw` (scope 内) | 可 | 同意済 |
| 当該 user の任意 ERC-20 transfer | **不可** | scope 外、Privy SDK が弾く |
| 当該 user の DEX swap | **不可** | scope 外 |
| 別 user の delegation を使った操作 | **不可** | token は user 単位 |
| 上限超過 supply | **不可** | scope 違反、execute_action が pre-check で reject |
| 期限切れ delegation での操作 | **不可** | execute_action が expires_at で reject |

### 5.2 scope 外を保証する 3 層防御

1. **token 側 (Privy)**: delegation token 自体が action と上限を内包し、Privy SDK が違反を拒否
2. **execute_action 側 (本クラス)**: 呼び出し前に scope と quota を pre-check し、違反なら即 raise
3. **DB 側 (ai_decisions / user_actions)**: 24h rolling 累積を集計し、scope を超える decision を `policy_violation` で reject

(3 つのうち 1 つでも残れば scope を破れない、という deny-by-default の設計)

### 5.3 audit log の取り方

- すべての `execute_action` 呼び出しを `user_actions` に記録
  - `delegation_token_id`(token そのものではなくハッシュ ID)
  - `action`, `amount_usdc`, `idempotency_key`
  - 紐づく `ai_decisions.id`(どの AI 判断による実行か)
- on-chain 実行に成功した場合は tx hash も同レコードに紐付け
- 失敗は `result=failed`, `error=...` で記録

`ai_decisions` と `user_actions` を join すれば、
「いつ・どの AI judgment が・どの user に・何 USDC で・何の action を実行したか」が再構成できる。

---

## 6. リスクと対策

### 6.1 Privy 障害

- delegation token 発行 / 検証が止まると AI judgment は **実行不能**
- 対策:
  - execute_action 側で Privy 5xx を検知したら ai_decisions に `privy_unavailable` で reject
  - scheduler はそのまま回し続け、復旧後に次サイクルから再開
  - ユーザ資金は Privy embedded wallet 内に温存され、運営側で焦げ付かない

### 6.2 鍵リカバリ

(参照: memory `privy_key_recovery_policy`)

- ユーザの Privy embedded wallet 自体のリカバリは Privy の recovery 経路に従う
- 本プロダクトは **user の鍵は一切保持しない**
- delegation token を運営が失った場合は、Privy 側に問い合わせて revoke + 再同意

### 6.3 delegated 漏洩時

- delegation token のハッシュ ID のみを DB / log に保存(token 本体は env / secret store)
- 漏洩疑いがあれば即 revoke:
  - operator 側スクリプトで全 active delegation を一括 revoke
  - user に再同意通知
  - blast radius は scope 内(他の任意操作はそもそも不可)に限定

### 6.4 quota 計算の整合性

- per-day 5000 USDC 上限はサーバ集計に依存
- 二重実行 (idempotency 不整合) で多重計上が起きると quota を誤って圧迫
- 対策:
  - `idempotency_key` を必須にし、execute_action で dedupe
  - 失敗時 retry も同一 key で実行

### 6.5 scope 拡張時の互換性

- Phase 3 後半で `compound:supply` などを追加する場合、既存 delegation は **新 scope を含まない**
- 新 action は再同意が必須(自動拡張しない deny-by-default)
- doc & onboarding 文言を都度更新

---

## 7. PoC 範囲(本 PR)

### 7.1 本 PR に含むもの

- `docs/internal/privy_delegated_signing_poc_design.md`(この doc)
- `backend/app/wallet/privy_delegated_client.py`
  - `DelegationScope` dataclass
  - `PrivyDelegatedClient` クラス骨格
  - 全メソッドは `NotImplementedError` で TODO

### 7.2 本 PR に含まないもの(別 PR)

- Privy SDK の実呼び出し
- `execute_action` の実 on-chain 署名 / 送信
- onboarding UI 画面の実装
- admin revoke スクリプト
- ai_judgment_scheduler との配線
- aave/client.py の修正(Tier-S なので別途設計)

### 7.3 後続 PR の想定順序

1. Privy SDK install & `request_delegation` 実装(staging のみ)
2. shadow mode: delegation を発行するが execute_action は NotImplementedError のまま、scope 検証のみ
3. `execute_action` 実装(staging で 1 user で実行検証)
4. `revoke` 実装 + admin スクリプト
5. onboarding UI(同意画面)
6. ai_judgment_scheduler 配線(Tier-S 慎重に)
7. production 投入(段階リリース・kill-switch 常備)

---

## 8. Open Questions

- per-day 5000 USDC は妥当か? AI judgment の典型 size を見て調整
- delegation 期限 90 日は KYC / 規制要件と整合するか?
- Privy delegated actions の SDK が `aave:supply` のような custom action key を受け付けるか、
  contract address + selector の組合せで指定するかは要検証(別 PR の 1 タスク目)
- revoke 完了は即時か、Privy 側で eventual か(レイテンシ要計測)

---

## 9. 参考

- 関連 memory: `privy_key_recovery_policy`
- 関連 doc: `docs/internal/staging_build_speedup_design.md`(doc format 参考)
- 関連コード(変更なし): `backend/app/aave/client.py`(Tier-S)
- 関連スケジューラ(変更なし): `backend/app/ai_judgment_scheduler.py`(Tier-S)
