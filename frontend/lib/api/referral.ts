// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getJson, postJson } from '@/lib/api/http'

export interface ReferralCodeResponse {
  referral_code: string
  share_url: string
}

export interface ReferredUser {
  id: number
  email_masked: string
  role: string
  created_at: string
}

export interface ReferralTransaction {
  type: string
  amount: string
  occurred_at: string
}

export interface ReferralEarnings {
  referral_count: number
  current_month_reward_jpy: string
  total_payout_jpy: string
  campaign_rate: string
  campaign_expires_month: string | null
}

/** LIFF チャット 紹介パネル用 */
export interface ReferredUserDetail {
  name: string
  joined_at: string
  status: string
  reward_jpy: string
}

export interface ReferralInfo {
  referral_count: number
  current_month_reward_jpy: string
  total_payout_jpy: string
  campaign_rate: string
  referral_code: string
  referred_users: ReferredUserDetail[]
}

export async function getReferralInfo(token: string): Promise<ReferralInfo> {
  return getJson<ReferralInfo>('/api/referral/earnings', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function createReferralCode(token: string): Promise<ReferralCodeResponse> {
  return postJson<ReferralCodeResponse>('/api/referral/code', {}, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export interface RegisterWithReferralPayload {
  email: string
  password: string
  username: string
  referral_code: string
  referred_consent: boolean
}

export interface RegisterWithReferralResponse {
  id: number
  email: string
  username: string
  role: string
  is_active: boolean
  access_token: string
  token_type: string
  expires_in: number
}

export function postReferralCode(token: string): Promise<ReferralCodeResponse> {
  return postJson<ReferralCodeResponse>('/partner/referral/code', {}, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getReferralList(token: string): Promise<ReferredUser[]> {
  return getJson<ReferredUser[]>('/partner/referral/list', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getReferralTransactions(token: string, userId: number): Promise<ReferralTransaction[]> {
  return getJson<ReferralTransaction[]>(`/partner/referral/users/${userId}/transactions`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getReferralEarnings(token: string): Promise<ReferralEarnings> {
  return getJson<ReferralEarnings>('/partner/referral/earnings', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function registerWithReferral(payload: RegisterWithReferralPayload): Promise<RegisterWithReferralResponse> {
  return postJson<RegisterWithReferralResponse>('/auth/register-with-referral', payload)
}
