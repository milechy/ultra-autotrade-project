# Phase 2-D session signer consent フロー設計（v4 完全おまかせ自動運用）

> 作成日: 2026-06-21 / v4 EPIC / Phase 2-D（AUTO 執行配線）
> 前提: Phase 1 spike で経路A GO確定（`docs/ops/v4_phase1_session_signer_spike.md`）。2-D-A（安全装置結線・PR #823）/ 2-D-B.1（authorization-signature・PR #824）完了。
> 本書は frontend + backend + Privy 公式 API の実機・実コード調査に基づく consent フロー設計。

---

## 目的

ユーザーが **自分の非カストディアル Smart Wallet(SCW) に、UATa サーバを session signer として（委譲枠の範囲で）許可**し、サーバがユーザー不在でも枠内の自動執行（Aave supply/withdraw 等）を行えるようにする。秘密鍵はユーザー側（Privy TEE）に残り、UATa は保持しない（非カストディアル不変）。

---

## 現状（調査で確定したギャップ）

- **frontend に session signer / delegation consent は一切無い**。`@privy-io/react-auth` v3.30 に `useSessionSigners` / `addSessionSigners` / `removeSessionSigners` / `useSigners().addSigners` は **install 済・未使用**。
- 現「managed モード」（`OpModePanel`）は **サーバ設定 `user_mode` を更新するだけ**で on-chain 委譲をしていない。実行は常にユーザー本人の Privy 署名（自己署名→submit-tx）。
- backend `/api/user/delegation`(grant/revoke, settings_router) は存在するが **frontend から未接続**。`delegation_grants.privy_policy_id`/`privy_signer_id` は列のみ・書き込みなし。
- 不変条件: `PrivyRootClient.tsx`「SCW owner はユーザー EOA のみ」/ `withdraw/page.tsx`「出金は委譲対象外・常に本人署名」。

---

## consent フロー（4 レイヤ）

Privy 公式レシピ "user-and-server-signers" + session signers に準拠。

### L0. サーバ authorization key の登録（アプリ単位・1回のみ）
- サーバの P-256 **公開鍵**を Privy に **key quorum** として登録（dashboard「Authorization keys → New key → Register key quorum instead」threshold=1、または REST API）。
- 返る **key quorum ID = `signerId`（= SERVER_SIGNER_ID）**。backend env に保持（`PRIVY_SERVER_SIGNER_ID`）。秘密鍵は env のみ（2-D-B.1 の `authorization_private_keys` 形式）。
- 鍵生成: `openssl ecparam -name prime256v1`（spike で実証済の形式）。

### L1. policy 作成（backend・grant 起票時）
- 委譲枠（`delegation_grants`: max_single_trade_pct / max_daily_trade_pct / hf_floor / allowed_protocols / allowed_assets / expires_at）→ **Privy policy** に写像（`wallet_policy.py` スキーマ → REST `POST /v1/policies`）。
- policy は Basic auth（app_id:app_secret）で作成可（wallet action ではないため authorization-signature 不要）。
- 返る `policy_id` を保持。

### L2. クライアント consent（frontend・ユーザー操作）
```ts
// SmartWalletsProvider 配下。ユーザーが「おまかせ運用を許可」を押す。
const { addSessionSigners } = useSessionSigners()  // または useSigners().addSigners
await addSessionSigners({
  address: userEmbeddedEoaAddress,        // SCW を制御する embedded EOA
  signers: [{ signerId: SERVER_SIGNER_ID, policyIds: [policyId] }],
})
```
- ユーザーが Privy UI で承認 → サーバ signer が policy スコープで EOA に紐づく。
- **出金系は policy スコープから除外**（不変条件維持）。

### L3. backend へ grant 確定
- frontend が `POST /api/user/delegation/grant` に枠＋ `privy_policy_id` ＋ `privy_signer_id`(=SERVER_SIGNER_ID) を送る → backend が `delegation_grants` を active で保存（既存 active は revoke して1ユーザー1枠）。
- 以後 PolicyEngine Rule8（2-D-A）が「有効枠あり」と判定し AUTO 執行を許可。

### L4. サーバ署名執行（backend・2-D-C）
- `scw_executor` が `sendCalls(eoaWalletId, {caip2, params:{calls}, authorization_context})` を Privy REST に投げる。`privy-authorization-signature` は 2-D-B.1 の `authorization_signature_header` で計算。
- 執行前ゲート（2-D-A）: HARD_STOP + risk_limiter %クランプ + Rule8 を必ず通過。Privy policy(TEE) と backend ゲートの**二重**で被害上限を縛る。

### revoke
- frontend `removeSessionSigners(...)` ＋ `POST /api/user/delegation/revoke` → grant を revoked、Privy 側 signer 解除。ユーザーはいつでも取消可（非カストディアル）。

---

## シーケンス（managed 化＝委譲オン）

```
User → frontend: 「おまかせ運用を許可」(OpModePanel managed)
frontend → backend: POST /delegation/prepare (枠) → backend: policy作成(L1) → policy_id 返却
frontend → Privy(client): addSessionSigners({address:EOA, signers:[{signerId:SERVER, policyIds:[policy_id]}]})
User → Privy UI: 承認
frontend → backend: POST /delegation/grant (枠 + privy_policy_id + privy_signer_id)
backend: delegation_grants 保存(active) → user_mode=managed
（以後）scheduler/executor → 枠内 AUTO 執行（2-A ゲート + Privy policy 二重）
```
失敗時ロールバック: addSessionSigners 失敗 → grant 作らず user_mode 据え置き。grant 保存失敗 → addSessionSigners を revoke。

---

## 実装作業（スライス割り）

| スライス | 層 | 主な作業 | Tier/リスク |
|---|---|---|---|
| **2-D-B.2** | backend | httpx Privy REST クライアント新設 + 実Privy live 受理検証 + L1 policy作成 + `/delegation/prepare`。L0 サーバ鍵 key quorum 登録（REST or dashboard・1回） | HUMAN-REVIEW（外部API/秘密鍵） |
| **2-D-C** | backend | `scw_executor`(sendCalls) + `_execute_aave_for_proposal` の委譲経路分岐（EOA直署名置換） | HUMAN-REVIEW（安全系本体） |
| **2-D-E（frontend）** | frontend | consent UI（OpModePanel managed 拡張）+ `useSessionSigners` 配線 + `lib/api/delegation.ts` + i18n 同意文言 + revoke | Tier B 中心（新規 component/別ファイル） |
| **2-D-D** | infra | 新フラグで staging-v4 shadow → 本番（%キャップ段階） | — |

---

## 設計上の決定事項・推奨

1. **consent UI 配置**: `OpModePanel`（liff-chat、SmartWalletsProvider 配下）の "managed" 選択時にステップ追加が最小。現状「確認なし即切替」を「委譲同意フロー経由」に変更。
2. **signerId の出所**: L0 で server 鍵を key quorum 登録し env 固定（全ユーザー共通の1サーバ signer）。per-user policy で枠を分離。
3. **policy 作成タイミング**: grant prepare 時（L1）。policy_id を addSessionSigners に渡す。
4. **出金除外**: policy の allowlist/method スコープに WITHDRAW/出金系を含めない（既存不変条件）。Phase 2-D の AUTO は SUPPLY 中心、WITHDRAW は本人署名維持を推奨。
5. **二重ガード維持**: Privy policy(TEE enforce) ＋ backend 2-A ゲート（HARD_STOP/risk_limiter/Rule8）。どちらか片方では本番有効化しない。

---

## 出典
- [Enabling users or servers to execute transactions | Privy](https://docs.privy.io/recipes/wallets/user-and-server-signers)
- [Session signers overview | Privy](https://docs.privy.io/wallets/using-wallets/session-signers/overview)
- 内部: `docs/ops/v4_phase1_session_signer_spike.md` / `backend/app/privy/auth_signature.py`(2-D-B.1) / `backend/app/proposals/router.py`(2-D-A) / `backend/app/users/models.py`(delegation_grants) / `frontend/lib/wallet/PrivyRootClient.tsx` / `frontend/app/(liff)/liff-chat/_components/panels/OpModePanel.tsx`
