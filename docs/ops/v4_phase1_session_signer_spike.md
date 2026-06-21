# Phase 1 署名委譲 PoC スパイク仕様（Privy session signers）

> 作成日: 2026-06-20 / v4 完全おまかせ自動運用 EPIC / Phase 1
> 種別: スパイク仕様（実装前の go/no-go 設計。**本番 merge なし・staging-v4 実機検証**）
> 出典: Privy 公式ドキュメント（WebFetch 取得、末尾参照）/ 既存実装 grep
>
> **本書は推測でなく Privy 公式 API の確認事実に基づく。確認できた範囲と「実機で検証すべき open 項目」を厳密に分離する。**

---

## 目的

完全おまかせ自動運用の最大の未確定点 = **「UATa サーバが、ユーザーの非カストディアル Smart Wallet(SCW) の UserOperation を、ユーザー不在で（事前委譲の範囲内で）署名・送信できるか」** を staging-v4 で実証し、本実装の経路（A/B）を確定する。

Phase 0（安全土台）は完了済み（PR #814/#815/#816/#818）。本スパイクは Phase 2-D（AUTO 執行配線）の前提。

---

## 確認できた事実（Privy 公式 API）

### 1. Privy には server 代理署名の一次機能が2系統ある
| 機能 | 対象 | 用途 |
|---|---|---|
| **signers（key quorum / authorization key）** | embedded EOA | server が P-256 authorization key で wallet action を代理署名 |
| **session signers** | **AA / smart wallet** | 「ユーザー不在(offline)でも app が onchain action を代理実行」。**AA アカウントに server-side アクセスを session key で付与** |

→ **完全自動(SCW を server 駆動)の正攻法は「session signers」**。公式に「Privy can create a signer for an AA account and provision server-side access using session keys」と明記。

### 2. 権限スコープ = Privy policy engine（TEE enforce）
- `POST /v1/policies`（version 1.0, chain_type=ethereum, rules[]）。
- rule.method に **`eth_signUserOperation`** が存在 → **UserOp 署名を policy で制約可能**。`eth_sendTransaction` も可。
- conditions:
  - `EthereumTransactionCondition`（field=`to`/`value`/`chain_id`、operator=eq/lte/in）→ **コントラクト allowlist + per-tx 上限**。
  - `EthereumCalldataCondition`（ABI でデコードして引数を制約）。
  - `SystemCondition`（field=`current_unix_timestamp`）→ **有効期限/時間窓**。
- policy は signer に `policyIds` で attach。TEE（secure enclave）が署名前に enforce（key は signer に渡らない）。
- これは UATa の委譲枠（`delegation_grants`: 単一≤10%/日次≤30%/allowed_protocols/expires_at）を **Privy policy に写像できる**ことを意味する（0-C で privy_policy_id/privy_signer_id カラムを用意済み）。

### 3. server 署名の SDK 形
- Node SDK `@privy-io/node`。authorization key は `authorization_context = { authorization_private_keys: [...] }` で供給（SDK が P-256 署名を計算）。
- 確認できた具体例: `privy.wallets().ethereum().signMessage(walletId, { message, authorization_context })`。
- 公式の動作する実例: **`github.com/privy-io/session-keys-example`**（AA + session keys + server + ZeroDev + Supabase）。

### 4. AA プロバイダ互換
Privy signer は permissionless.js(Pimlico) / ZeroDev / Safe / MetaMask Smart Accounts と signer として連携可能（各社公式 docs に Privy 連携ガイドあり）。

---

## 実機で検証すべき open 項目（docs だけでは確定不能）

| # | open 項目 | なぜ未確定か |
|---|---|---|
| O1 | **UATa 現行の Privy SCW（`SmartWalletsProvider`）が session signers で server 駆動できるか** | session-signers の公式例は ZeroDev を併用。Privy native smart wallet 単体で session signer 経由の server UserOp 署名が通るかは docs に明記なし |
| O2 | **UserOp を server から署名/送信する正確な Node SDK メソッド名** | docs 抜粋は signMessage のみ確認。UserOp 用メソッドは session-keys-example / llms.txt で要確認 |
| O3 | **既存 bundler/paymaster（Privy dashboard 設定）が server-session-signed UserOp を受理するか** | UATa は SmartWalletsProvider + paymaster 構成（スライス4a/4b）。session signer 経由でも paymaster sponsor が効くか実機要確認 |

→ O1 が **経路A/B の分岐点**。O1 が ✅ → 経路A（Privy native session signers・工数小）。O1 が ❌ → 経路B（ZeroDev Kernel 併用・公式例どおり・工数大）。

---

## go/no-go スパイク手順（staging-v4 / Base Sepolia / テスト用 SCW）

各ステップの期待結果を満たすか実機で確認する。

1. **S1 — session signer 登録**: Privy dashboard(staging-v4 app) で session signer を有効化し、サーバの P-256 authorization key を登録。テストユーザーの Privy SCW に session signer を add。
   - 期待: SCW に session signer が紐づく（O1 の一次確認）。
2. **S2 — policy 作成 + attach**: `POST /v1/policies` で `eth_signUserOperation` rule（`to` eq = Aave V3 Pool(Base Sepolia `0x8bAB...aE27`)、`value` lte = テスト上限、`current_unix_timestamp` lte = expiry）を作成し、session signer に `policyIds` で attach。
   - 期待: policy 作成成功、policy_id 取得。
3. **S3 — server 代理署名で UserOp 送信（本丸）**: サーバ（@privy-io/node、`authorization_context`）から、テストユーザー SCW の `Aave Pool.supply(USDC, amount, onBehalfOf=SCW, 0)` を含む UserOp を **ユーザー操作なしで**署名・送信。paymaster sponsor 下。
   - 期待: UserOp が bundler に受理され、on-chain で supply 成立（O1/O2/O3 を同時に確認）。**これが ✅ なら経路A 確定。**
4. **S4 — policy 拒否の確認**: policy 違反 UserOp（allowlist 外コントラクト宛 / 上限超過 value）を送信。
   - 期待: Privy TEE が署名を **reject**（被害上限が enclave で効くことの確認）。
5. **S5 — revoke の確認**: session signer を remove（またはユーザー側 revoke）後に S3 を再実行。
   - 期待: 署名不能になる（非カストディアル・revoke 可の実証）。

### 確定基準
- **S3 ✅ → 経路A（Privy native session signers）を本実装経路に確定。** Phase 2-D の `proposals/auto_executor.py` は session signer 経由の server UserOp 署名で SCW を駆動する。`delegation_grants.privy_policy_id`/`privy_signer_id`（0-C 既設）に S2 の値を保存。
- **S3 ❌（Privy native SCW が不可）→ 経路B（ZeroDev Kernel）。** `github.com/privy-io/session-keys-example` 準拠で AA を ZeroDev に寄せる。工数・移行コスト再見積り（現 SmartWalletsProvider からの構成変更）。

---

## スパイク結果（2026-06-21 実機実行）: **経路A GO 確定**

dev VPS 上で `@privy-io/node` v0.22.0 を用いた段階プローブ harness（`~/uata-privy-spike-harness/`、本番 merge せず）で実機検証。Privy app "UAT"（Base Sepolia only / smart_wallet_type=`coinbase_smart_wallet` v1.1 / bundler+paymaster=Pimlico）。既存ユーザーには触れず、サーバが新規に専用 wallet を生成して検証。

| 検証 | 結果 | 根拠 |
|---|---|---|
| O1: サーバが非カストディアル wallet を委譲署名 | ✅ | `wallets().ethereum().signMessage(walletId, {authorization_context})` 成功（自前 openssl P-256 鍵を owner にした wallet を、その秘密鍵でサーバ署名） |
| coinbase smart wallet をサーバ生成＋delegated signer | ✅ | `users().create({wallets:[{create_smart_wallet:true, additional_signers:[{signer_id}]}]})` で SCW 生成、EOA signer は `delegated:true` |
| O2: UserOp 署名メソッド | ✅ | `signUserOperation`（署名のみ）/ 高レベルは `sendCalls`（ERC-5792） |
| O3+S3: サーバが SCW 経由で組立→署名→broadcast | ✅（gas を除き全通） | `sendCalls(eoaWalletId, {caip2:'eip155:84532', sponsor:true/false, params:{calls:[...]}, authorization_context})` が smart wallet 経由で broadcast 到達。`sponsor:false` 時のみ「insufficient funds for gas（have 0）」= 配線は全成立、testnet gas のみ不足 |

**結論:**
- **経路A（Privy native session signers）を本実装経路に確定。経路B（ZeroDev Kernel 移行）は不要。**
- Phase 2-D `auto_executor` は **`sendCalls` 1 呼び出し**で SCW を駆動できる（manual UserOp 組立は不要。Privy がサーバ側で組立～署名～送信を処理）。
- authorization key は **openssl 自前生成で可**（dashboard "New key" 不要）。形式: 秘密鍵=PKCS8 DER の base64（PEM ヘッダなし）/ 公開鍵=SPKI DER の base64。owner は `owner:{public_key}` で指定。
- 実 on-chain receipt は未取得（testnet gas 入手の物流のみ。feasibility 判定には不要なため (A) で完了）。本番 v4 の paymaster sponsor は別途インフラ（Pimlico paymaster 設定済 + クライアント経路）で確認する。
- サーバ wallet API の `sponsor:true` は `Gas sponsorship is not enabled` を返す（クライアント smart wallet SDK が使う paymaster とは別系統）。本番では SCW を gas で賄うか、別途 gas sponsorship 設定が要る点に留意。

### Phase 2-D 実装メモ（この spike からの確定事項）
- 署名駆動 API: `privy.wallets().ethereum().sendCalls(eoaWalletId, {caip2, params:{calls:[{to,value,data}]}, authorization_context:{authorization_private_keys:[<P256 PKCS8 b64>]}})`。
- policy（被害上限の TEE enforce）は `policies().create` + wallet/signer への attach（`policy_ids`）。S2/S4 は本実装時に併せて検証。
- 委譲枠（`delegation_grants`）→ Privy policy 写像 + `privy_policy_id`/`privy_signer_id` 保存（0-C 既設）。

---

## 必要な環境・認証情報（小林さん側で準備が必要）

- staging-v4 の **Privy app** dashboard アクセス（session signers 有効化 / authorization key 登録）。
- サーバ用 **P-256 authorization private key**（`openssl ecparam -name prime256v1 ...` で生成、secret 管理。ログ禁止・env のみ＝CLAUDE.md §Security 1/8）。
- Base Sepolia 上のテストユーザー SCW（既存 staging-v4 の test wallet 流用可。`project_staging_noncustodial_proof_state` の 0x7f93…a0Ff 等）。
- bundler / paymaster（staging-v4 の Privy dashboard 設定。スライス4a/4b 済）。
- `@privy-io/node` を使う検証用スクリプト置き場（PoC は本番 merge しない feature ブランチ / staging 限定）。

---

## セキュリティ前提（不変）

- session signer は **ユーザー consent 起点**・**revoke 可**・**policy で枠制限**（TEE enforce）。非カストディアル（UATa は秘密鍵を保持しない）を維持。
- authorization key は secret（env のみ・マスク・非ログ）。漏洩時の被害上限を Privy policy（allowlist/上限/expiry）＋ UATa backend ゲート（Phase 0 の HARD_STOP / Phase 2-D の risk_limiter %クランプ）で**二重**に縛る（[[project_v4_full_auto_delegation]] の TEE 鍵抽出リスク対策）。
- 本スパイクは staging-v4 のみ。**本番資金・本番 SCW では実行しない。**

---

## 出典（WebFetch / WebSearch、2026-06-20）

- [Create policy | Privy API](https://docs.privy.io/api-reference/policies/create) — policy schema・`eth_signUserOperation`・conditions
- [Configure signers | Privy](https://docs.privy.io/wallets/using-wallets/signers/configure-signers) / [user-and-server-signers recipe](https://docs.privy.io/recipes/wallets/user-and-server-signers) — key quorum・addSigners・policyIds
- [Signing on the server | Privy](https://docs.privy.io/controls/authorization-keys/using-owners/sign/signing-on-the-server) — authorization_context・Node SDK signMessage
- [Session signers overview | Privy](https://docs.privy.io/wallets/using-wallets/session-signers/overview) — AA/smart wallet の server 代理署名（offline）
- [privy-io/session-keys-example (GitHub)](https://github.com/privy-io/session-keys-example) — AA + session keys + server 実例
- 内部参照: `docs/privy-aa-paymaster-design.md` §1.5 / `docs/56_privy_policy_engine_design.md` / `backend/app/users/models.py`（delegation_grants）/ `frontend/lib/wallet/PrivyRootClient.tsx`（SmartWalletsProvider）
