// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/lib/api/delegation.ts
//
// v4 Phase 2-D-E: 委譲（おまかせ運用）consent フローの API クライアント。
// backend: /api/user/delegation/{prepare,grant,revoke} + GET /api/user/delegation。
//
// 非カストディアル: backend は policy 作成と grant 記録のみ。実際の session signer 付与は
// frontend の Privy useSigners().addSigners が行う（秘密鍵はユーザー側 TEE に残る）。
// prepare は backend が dormant（L0 未登録 / フラグ off）のとき 503 を返す
// → DelegationNotReadyError として扱い、UI は「準備中」表示にフォールバックする。

import { getAuthToken } from "@/lib/auth/token-key"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export interface DelegationGrantParams {
  max_single_trade_pct: string
  max_daily_trade_pct: string
  hf_floor: string
  allowed_protocols: string[]
  allowed_assets: string[]
  expires_in_days: number
}

export interface DelegationGrantExtra {
  privy_policy_id?: string
  privy_signer_id?: string
  // Privy 内部 wallet ID（アドレスではない）。addSigners 成功直後のみ解決可能
  // （ログイン時点では未委譲で null。Privy SDK 仕様）。委譲(SCW)執行の
  // wallet_sendCalls が要求する識別子で、渡すと users.privy_wallet_id へ保存される。
  privy_wallet_id?: string
}

export interface DelegationPrepareResponse {
  privy_policy_id: string
  privy_signer_id: string
  chain_name: string
  expires_at: string
}

export interface DelegationGrantResponse {
  id: number
  status: string
  wallet_address: string | null
  max_single_trade_pct: string
  max_daily_trade_pct: string
  hf_floor: string
  allowed_protocols: string[]
  allowed_assets: string[]
  consent_at: string
  expires_at: string
  revoked_at: string | null
  privy_policy_id: string | null
  privy_signer_id: string | null
}

/** backend が委譲 policy 作成を未有効化（dormant: L0 未登録 / フラグ off）= 503。 */
export class DelegationNotReadyError extends Error {
  constructor(message = "delegation policy preparation is not enabled") {
    super(message)
    this.name = "DelegationNotReadyError"
  }
}

/** consent の既定枠。将来 UI から調整可能にする（現状は保守的な単一上限）。 */
export const DEFAULT_DELEGATION_PARAMS: DelegationGrantParams = {
  max_single_trade_pct: "10",
  max_daily_trade_pct: "30",
  hf_floor: "1.6",
  allowed_protocols: ["aave"],
  allowed_assets: ["USDC"],
  expires_in_days: 90,
}

async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = getAuthToken()
  if (!token) throw new Error("auth token missing")
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })
}

/** L1: 委譲枠から Privy policy を作成し signer/policy id を得る。dormant 時は 503 → throw。 */
export async function prepareDelegation(
  params: DelegationGrantParams
): Promise<DelegationPrepareResponse> {
  const res = await authedFetch("/api/user/delegation/prepare", {
    method: "POST",
    body: JSON.stringify(params),
  })
  if (res.status === 503) throw new DelegationNotReadyError()
  if (!res.ok) throw new Error(`delegation prepare failed: HTTP ${res.status}`)
  return res.json()
}

/** L3: consent 済みの枠 + Privy 識別子を保存して grant を確定する。 */
export async function grantDelegation(
  params: DelegationGrantParams & DelegationGrantExtra
): Promise<DelegationGrantResponse> {
  const res = await authedFetch("/api/user/delegation/grant", {
    method: "POST",
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`delegation grant failed: HTTP ${res.status}`)
  return res.json()
}

/** 委譲枠を取消す（冪等）。 */
export async function revokeDelegation(): Promise<DelegationGrantResponse | null> {
  const res = await authedFetch("/api/user/delegation/revoke", { method: "POST" })
  if (!res.ok) throw new Error(`delegation revoke failed: HTTP ${res.status}`)
  return res.json()
}

/** 現在有効な委譲枠を返す（無ければ null）。 */
export async function getDelegation(): Promise<DelegationGrantResponse | null> {
  const res = await authedFetch("/api/user/delegation", { method: "GET" })
  if (!res.ok) throw new Error(`delegation get failed: HTTP ${res.status}`)
  return res.json()
}
