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

/**
 * 「完全おまかせ」の運用方針。
 *
 * **単一の真実源は backend の `user.risk_mode`**。プロトコル選択は 2 段で効く:
 *   - risk_mode → `RISK_MODE_PROTOCOLS` → **提案が生成されるか**（ai_judgment_scheduler）
 *   - grant.allowed_protocols → **生成済み提案が broadcast されるか**（proposals/router）
 * 両方が揃わないと Pendle は動かないため、ここで 3 つ目の概念を作らず risk_mode に対応させる。
 */
export type ManagedScope = "safety" | "yield"

/** 運用方針 → risk_mode（backend `RiskMode` enum の内部値。リネーム禁止）。 */
export const SCOPE_TO_RISK_MODE: Record<ManagedScope, string> = {
  safety: "conservative",
  yield: "aggressive",
}

/**
 * 運用方針 → 委譲プロトコル。backend `delegatable_protocols_for_risk_mode()` と一致させること。
 *
 * aggressive の商品定義は {aave, lido, pendle} だが lido は委譲経路が未対応で、渡すと
 * prepare が 502（fail-closed）になる。ここは**委譲可能集合との積**を持つ。
 */
const SCOPE_PROTOCOLS: Record<ManagedScope, string[]> = {
  safety: ["aave"],
  yield: ["aave", "pendle"],
}

/** consent の既定枠（方針によらない共通の上限）。 */
const BASE_DELEGATION_LIMITS = {
  max_single_trade_pct: "10",
  max_daily_trade_pct: "30",
  hf_floor: "1.6",
  allowed_assets: ["USDC"],
  expires_in_days: 90,
} as const

/** 運用方針から consent する委譲枠を組み立てる。prepare / grant で同じ値を使うこと。 */
export function delegationParamsForScope(scope: ManagedScope): DelegationGrantParams {
  return {
    ...BASE_DELEGATION_LIMITS,
    allowed_assets: [...BASE_DELEGATION_LIMITS.allowed_assets],
    allowed_protocols: [...SCOPE_PROTOCOLS[scope]],
  }
}

/** 委譲枠が Pendle を許可しているか（broadcast 側のゲート）。 */
export function grantAllowsPendle(grant: DelegationGrantResponse | null): boolean {
  if (!grant) return false
  return (grant.allowed_protocols ?? []).map((p) => p.trim().toLowerCase()).includes("pendle")
}

/**
 * 実効の運用方針。**2 つのゲートが両方通ったときだけ** "yield"。
 *
 * Pendle が実際に流れるには「risk_mode=aggressive（提案が生成される）」と「grant に pendle
 * （broadcast される）」の両方が要る。片方だけで「利回り重視」と表示すると UI が嘘になるので、
 * 論理積を実効値とする。
 */
export function effectiveScope(
  grant: DelegationGrantResponse | null,
  riskMode: string | null | undefined
): ManagedScope {
  return grantAllowsPendle(grant) && riskMode === SCOPE_TO_RISK_MODE.yield ? "yield" : "safety"
}

/**
 * 「利回り重視のつもりだが権限が追いついていない」状態か（再署名が必要）。
 *
 * risk_mode が grant より先行すると、Pendle 提案は生成されるのに broadcast されず approved の
 * まま滞留する。この不整合は黙って放置せず UI で再署名を促す。
 */
export function needsReconsentForYield(
  grant: DelegationGrantResponse | null,
  riskMode: string | null | undefined
): boolean {
  return riskMode === SCOPE_TO_RISK_MODE.yield && !grantAllowsPendle(grant)
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

/** backend が当該 risk_mode をまだ解禁していない（`PHASE_1_ALLOWED_RISK_MODES` = 403）。 */
export class RiskModeNotAvailableError extends Error {
  constructor(message = "risk mode is not available yet") {
    super(message)
    this.name = "RiskModeNotAvailableError"
  }
}

/** Pendle 開示（満期ロック / 裏付け / スリッページ）への同意を記録する（冪等）。 */
export async function submitAggressiveConsent(): Promise<void> {
  const res = await authedFetch("/api/user/aggressive-consent", { method: "POST" })
  if (!res.ok) throw new Error(`aggressive consent failed: HTTP ${res.status}`)
}

/**
 * risk_mode を更新する。**委譲枠を確定した後に呼ぶこと**。
 *
 * risk_mode が grant より先行すると Pendle 提案は生成されるのに broadcast されず滞留する
 * （`needsReconsentForYield` 参照）。403 = backend 未解禁、412 = 開示未同意。
 */
export async function updateRiskMode(mode: string): Promise<void> {
  const res = await authedFetch("/auth/risk-mode", {
    method: "PUT",
    body: JSON.stringify({ mode }),
  })
  if (res.status === 403 || res.status === 412) throw new RiskModeNotAvailableError()
  if (!res.ok) throw new Error(`risk mode update failed: HTTP ${res.status}`)
}
