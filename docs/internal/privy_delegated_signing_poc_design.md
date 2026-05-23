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

| 方式 | scope | 鍵管理 | UX | リスク | SLA (vendor) | latency (実行 1 件) | 月間 cost オーダー | 採否 |
|---|---|---|---|---|---|---|---|---|
| Privy delegated actions | 細かい | Privy 保管 | 良 | Privy 依存 | Privy SaaS SLA (公称 99.9%) | request: ~150-400ms / execute: ~400-1200ms (Privy + RPC) | Privy MAU 課金 + RPC 課金 (小〜中) | 候補A |
| Privy session signer | 中 | Privy 保管 + session | 良 | session 期限 | 同上 | execute: ~300-900ms (session 内は SDK ローカル + RPC) | 同上(課金体系は同じ) | 候補B |
| server-side wallet | 自由 | 自社 KMS | 中 | 鍵漏洩リスク | KMS SLA に従属 (AWS KMS 99.999%) | execute: ~200-700ms (KMS sign + RPC) | KMS リクエスト課金 + RPC (中) | 不採用 |

> latency は staging で実測予定の **想定オーダー**(PoC 検証 task に含む / open question §8)。
> cost は MAU 規模で大きく変わるため「オーダー比較」のみ。詳細試算は別 doc。

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

### 3.4 scope JSON schema

delegation token に焼き込む scope の正規スキーマは以下のとおり。
これは `backend/app/wallet/delegation_scope.py` の `DelegationScope` と 1:1 対応する。

```json
{
  "actions": ["aave:supply", "aave:withdraw"],
  "max_amount_per_tx_usdc": 1000,
  "max_amount_per_day_usdc": 5000,
  "expires_at_unix": 1748000000,
  "revoke_token": "rvk_3f8a...redacted..."
}
```

| field | type | 制約 | 備考 |
|---|---|---|---|
| `actions` | `string[]` | 非空 / 全要素が `SUPPORTED_ACTIONS` の subset | `aave:supply` / `aave:withdraw` / `aave:repay` のみ |
| `max_amount_per_tx_usdc` | `int` | `> 0` | 1 tx 上限 (USDC 整数, PoC) |
| `max_amount_per_day_usdc` | `int` | `> 0` かつ `>= max_amount_per_tx_usdc` | 24h rolling 上限 |
| `expires_at_unix` | `int` (epoch sec) | 発行時に未来 | 期限切れ後の execute_action は即拒否 |
| `revoke_token` | `string` | 非空 | 運営側 revoke 経路の opaque handle、**ログに verbatim 載せない** |

forward-compat: 不明 key は受信側で **無視** する (`DelegationScope.from_jwt_claim` 参照)。
新 field を追加する場合も既存 token の互換は保つ。

### 3.5 Privy SDK 呼出例(擬似コード)

実 SDK 呼出は別 PR で確定するが、設計検討用の擬似コードを示す。

#### request_delegation

```python
# backend/app/wallet/privy_delegated_client.py の実装イメージ(skeleton 維持中)
scope = DelegationScope(
    actions=["aave:supply", "aave:withdraw"],
    max_amount_per_tx_usdc=1000,
    max_amount_per_day_usdc=5000,
    expires_at_unix=int(time.time()) + 90 * 86400,
    revoke_token=secrets.token_urlsafe(24),
)
scope.assert_consistent()

# Privy delegated actions endpoint (想定):
#   POST https://auth.privy.io/api/v1/users/{did}/delegations
#   Authorization: Basic base64(app_id:app_secret)
#   body: { "scope": scope.to_jwt_claim() }
resp = privy_sdk.delegations.create(
    user_did=user_privy_did,
    scope=scope.to_jwt_claim(),
)
delegation_token = resp["delegation_token"]   # opaque
# 永続化は token の **ハッシュ ID** のみ。token 本体は secret store。
record_audit(session, AuditEvent(
    event_type="delegation.granted",
    user_id=user_id,
    scope=scope,
    timestamp=int(time.time()),
))
```

#### execute_action

```python
# scope 内チェック → Privy 呼出 → audit
if not scope.allows_action(action):
    raise DelegationScopeViolation(action)
if not scope.allows_amount(amount_usdc):
    raise DelegationScopeViolation(f"amount {amount_usdc} > per-tx cap")
if scope.is_expired():
    raise DelegationScopeViolation("expired")

# per-day cap は audit 集計(下記 §5.3 の SQL)で別途 enforce

# POST https://auth.privy.io/api/v1/delegations/{token}/execute
#   body: { "action": "aave:supply", "amount_usdc": 500, "idempotency_key": "..." }
resp = privy_sdk.delegations.execute(
    delegation_token=delegation_token,
    action=action,
    params={"amount_usdc": amount_usdc},
    idempotency_key=idempotency_key,
)
tx_hash = resp.get("tx_hash")
record_audit(session, AuditEvent(
    event_type="execute_action.success" if tx_hash else "execute_action.attempt",
    user_id=user_id,
    scope=scope,
    action=action,
    amount=amount_usdc,
    tx_hash=tx_hash,
    timestamp=int(time.time()),
    idempotency_key=idempotency_key,
))
```

#### revoke

```python
# POST https://auth.privy.io/api/v1/delegations/{token}/revoke
ok = privy_sdk.delegations.revoke(delegation_token=token)
record_audit(session, AuditEvent(
    event_type="delegation.revoked",
    user_id=user_id,
    timestamp=int(time.time()),
    reason="user_requested",  # or "operator_runbook" / "leak_suspected"
))
```

### 3.6 revoke 経路

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

P1 (Privy MVP) onboarding の最後に、以下の専用画面を挟む。
ASCII ワイヤフレーム(モバイル幅, 360-420px 想定)を示す。

#### 同意取得画面 (onboarding step 5/5)

```
+--------------------------------------------------+
|  <-- back                            step 5 / 5  |
+--------------------------------------------------+
|                                                  |
|   自動運用に必要な権限を確認                     |
|   ---------------------------------------------  |
|                                                  |
|   ultra-autotrade は、あなたの代わりに           |
|   以下の操作 **だけ** を実行します:              |
|                                                  |
|     [v] AAVE への USDC supply                    |
|     [v] AAVE からの USDC withdraw                |
|                                                  |
|   制限:                                          |
|     - 1 回あたり最大       1,000 USDC            |
|     - 1 日あたり最大       5,000 USDC            |
|     - 有効期限             90 日                 |
|                                                  |
|   許可しないこと:                                |
|     [x] 任意の宛先への送金                       |
|     [x] DEX swap / 別 protocol 呼出              |
|     [x] 上限を超える操作                         |
|                                                  |
|   取消は「設定 > 自動運用の権限」から            |
|   いつでも可能です。                             |
|                                                  |
|   +--------------------------------------------+ |
|   |          [ 同意して開始する ]              | |
|   +--------------------------------------------+ |
|                                                  |
|       [ 後で(自動運用 OFF で続ける)]            |
|                                                  |
+--------------------------------------------------+
```

#### 同意 → Privy ポップアップ(SDK 表示・参考)

```
       +-----------------------------------+
       |  Privy:  delegation を承認しますか? |
       |  ----------------------------------|
       |   発行元:    ultra-autotrade       |
       |   actions:                         |
       |     - aave:supply                  |
       |     - aave:withdraw                |
       |   max/tx:    1,000 USDC            |
       |   max/day:   5,000 USDC            |
       |   有効期限:  2026-08-21            |
       |                                    |
       |   [ 拒否 ]            [ 承認 ]     |
       +-----------------------------------+
```

#### 設定画面: 自動運用の権限(後日アクセス)

```
+--------------------------------------------------+
|  設定 > 自動運用の権限                            |
+--------------------------------------------------+
|  状態:  ON(2026-08-21 まで有効)                  |
|                                                  |
|  許可中:                                         |
|    - aave:supply         (~ 1,000 / tx)          |
|    - aave:withdraw       (~ 1,000 / tx)          |
|  24h 使用量:    1,250 / 5,000 USDC                |
|                                                  |
|  +------------------------+  +-----------------+ |
|  | [ 90 日延長(再同意) ] |  | [ 取消(revoke)] | |
|  +------------------------+  +-----------------+ |
|                                                  |
|  履歴 (直近 5 件):                               |
|    2026-05-23 09:15  supply  +300 USDC  ok       |
|    2026-05-23 03:02  supply  +200 USDC  ok       |
|    2026-05-22 21:48  withdraw  -150 USDC  ok     |
|    2026-05-22 14:11  supply  +500 USDC  ok       |
|    2026-05-22 09:30  supply  +100 USDC  ok       |
|                                                  |
+--------------------------------------------------+
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

audit イベントの実体は `backend/app/wallet/audit.py` の `AuditEvent` Pydantic model に対応する。
`user_actions` テーブルが未存在 / 未配線の環境では、`record_audit()` が INFO ログに fallback して
caller path を絶対に壊さない設計とする(PoC 期間中)。

#### 5.3.1 join SQL 例: 「ある user の今日の execute 履歴」

```sql
-- 当該 user の 24h 内の execute_action と、それを駆動した ai_decision を再構成
SELECT
  ua.timestamp_unix,
  ua.action,
  ua.amount_usdc,
  ua.tx_hash,
  ua.event_type,
  ua.reason,
  ad.id            AS ai_decision_id,
  ad.judgment      AS ai_judgment,
  ad.confidence    AS ai_confidence,
  ad.reason        AS ai_reason
FROM user_actions ua
LEFT JOIN ai_decisions ad
  ON ad.id = ua.ai_decision_id
WHERE ua.user_id = :user_id
  AND ua.event_type IN (
        'execute_action.attempt',
        'execute_action.success',
        'execute_action.failure'
      )
  AND ua.timestamp_unix >= EXTRACT(EPOCH FROM (now() - INTERVAL '24 hours'))::int
ORDER BY ua.timestamp_unix DESC;
```

#### 5.3.2 join SQL 例: per-day quota 集計(scope enforcement)

```sql
-- per-day rolling cap (5000 USDC) の enforcement に使う集計
SELECT
  COALESCE(SUM(ua.amount_usdc), 0) AS used_usdc_24h
FROM user_actions ua
WHERE ua.user_id = :user_id
  AND ua.event_type IN ('execute_action.success', 'execute_action.attempt')
  AND ua.amount_usdc IS NOT NULL
  AND ua.timestamp_unix >= EXTRACT(EPOCH FROM (now() - INTERVAL '24 hours'))::int;
```

#### 5.3.3 join SQL 例: policy_violation 監視

```sql
-- scope 違反が起きた decision を直近 7 日でリストアップ
SELECT
  ua.timestamp_unix,
  ua.user_id,
  ua.action,
  ua.amount_usdc,
  ua.reason          AS violation_reason,
  ad.judgment        AS ai_judgment,
  ad.confidence      AS ai_confidence
FROM user_actions ua
LEFT JOIN ai_decisions ad
  ON ad.id = ua.ai_decision_id
WHERE ua.event_type = 'policy_violation'
  AND ua.timestamp_unix >= EXTRACT(EPOCH FROM (now() - INTERVAL '7 days'))::int
ORDER BY ua.timestamp_unix DESC;
```

これらの join により、
「いつ・どの AI judgment が・どの user に・何 USDC で・何の action を実行したか / なぜ拒否されたか」
が再構成できる。

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

### 6.3 delegated 漏洩時(runbook)

delegation token のハッシュ ID のみを DB / log に保存(token 本体は env / secret store)。
漏洩疑いを **検知** した瞬間に以下の手順を実行する。

#### 6.3.1 operator runbook(運営側起点)

| step | 操作 | 担当 | 想定時間 | 出力裏取り |
|---|---|---|---|---|
| 1 | `disable_ai_scheduler` を ON にし、scheduler の新規 execute_action を全停止 | on-call | < 1 min | `SELECT key, value FROM feature_flags WHERE key='disable_ai_scheduler'` が `true` |
| 2 | 影響範囲を特定(漏洩したのは全体か特定 user か) | on-call | 5-10 min | log / alert 内容 + `user_actions` の event_type='execute_action.*' 直近 24h |
| 3 | 一括 revoke script を staging で dry-run | on-call | 2 min | dry-run log に対象 user_id 一覧が出ること |
| 4 | 一括 revoke script を prod で実行 | on-call (+1 reviewer) | 5 min | `PrivyDelegatedClient.revoke()` の戻り値 True が全件 / `user_actions` に `delegation.revoked` row |
| 5 | 影響 user に再同意通知を送信 | comms | 10 min | 通知 send result の log |
| 6 | `disable_ai_scheduler` を OFF に戻すかは、原因究明後に判断 | on-call | — | 再発防止確認後 |
| 7 | postmortem を起票 | on-call | 24h 以内 | postmortem doc URL |

> **重要:** step 1 と step 4 は順序厳守。step 1 をスキップすると、revoke 完了までの間に
> 漏洩 token で execute されうる(Privy 側 revoke が eventual の可能性、§8 open question)。

#### 6.3.2 user runbook(ユーザ自己起点)

| step | 操作 | UI 経路 | 完了確認 |
|---|---|---|---|
| 1 | 設定 > 自動運用の権限 を開く | アプリ内 | 画面が「ON」表示であること |
| 2 | 「取消(revoke)」を tap | アプリ内 | 確認ダイアログ |
| 3 | API `POST /api/wallet/delegation/revoke` を発火 | アプリ内 | 200 OK + `user_actions` に `delegation.revoked` reason=`user_requested` |
| 4 | 画面が「OFF」に切り替わる | アプリ内 | 状態表示 = OFF |
| 5 | Privy dashboard 側でも revoke 反映を確認(任意) | Privy 経路 | dashboard 表示 |

#### 6.3.3 blast radius の最小化

漏洩しても scope 外(任意 transfer / DEX / 他 protocol)は **そもそも実行不可** という前提があるため、
最悪ケースでも被害は「scope 内の上限 × 漏洩 token 数 × revoke 反映までの時間窓」に閉じる。
これを更に縮めるため:

- per-tx / per-day 上限を保守的に設定(PoC: 1k / 5k USDC)
- expires_at を 90 日に制限(忘却 revoke の自然失効)
- `disable_ai_scheduler` kill-switch を runbook の step 1 に固定配置

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
  - `PrivyDelegatedClient` クラス骨格
  - 全メソッドは `NotImplementedError` で TODO
  - docstring に各メソッドの引数 / 戻り値 / 失敗パスを明文化
- `backend/app/wallet/delegation_scope.py`(本 PR で新規・skeleton ではなく **実データクラス**)
  - `DelegationScope` Pydantic model(serialize / deserialize 可能)
  - `to_jwt_claim()` / `from_jwt_claim()`
  - `actions` subset validation / `expires_at_unix` 未来検証 / `assert_consistent()` で cross-field
- `backend/app/wallet/audit.py`(本 PR で新規・実 helper)
  - `AuditEvent` Pydantic model
  - `record_audit(session, event)` — `user_actions`(P0-6)に書込、未存在時は INFO log fallback

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

### 7.4 段階的ロールアウト計画

production 投入は **3 フェーズの段階リリース**。各フェーズは前段の SLO 達成が条件。

| phase | 対象範囲 | 期間 | 終了判定 SLO | 失敗時のロールバック |
|---|---|---|---|---|
| **Phase 3-α** | 10% users(opt-in / 内部ベータ user) | 2 週間 | execute_action 成功率 >= 99% / `policy_violation` 0 件 / Privy 5xx < 0.5% | `disable_ai_scheduler` ON + 全 delegation revoke |
| **Phase 3-β** | 50% users(ハッシュ % で振り分け) | 3 週間 | 上記 SLO 維持 + per-day quota 整合性 100% / kill-switch 訓練 1 回完了 | feature flag `delegated_signing_enabled` を 10% に戻す |
| **Phase 3-GA** | 100% users | 継続 | 上記 SLO + revoke レイテンシ p95 < 60s(open question §8) | flag を 50% に戻す + postmortem |

#### 7.4.1 各 phase の振り分け方

- feature flag `delegated_signing_pct: int` を導入(0-100)
- 振り分けキー: `sha256(user_id).hex()[:8]` を 0-99 に丸めて比較
- α/β は cohort 固定で進める(同じ user が phase をまたいでも変わらない)

#### 7.4.2 kill-switch 訓練

- Phase 3-β 中に必ず 1 回、staging で「漏洩疑い → revoke 全件」訓練を実施
- runbook §6.3.1 の step 1-5 を 30 分以内に完了できることを確認
- 訓練ログを postmortem テンプレートに添付

#### 7.4.3 各 phase の通知方針

| phase | 対象 user への事前通知 | 全社通知 |
|---|---|---|
| 3-α | opt-in 取得時に説明済(同意画面) | engineering only |
| 3-β | onboarding 内で表示 | engineering + product + support |
| 3-GA | press release / プロダクト内 banner | 全社 + 外部 |

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
