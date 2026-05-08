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
  return postJson<ReferralCodeResponse>('/referral/code', {}, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getReferralList(token: string): Promise<ReferredUser[]> {
  return getJson<ReferredUser[]>('/referral/list', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getReferralTransactions(token: string, userId: number): Promise<ReferralTransaction[]> {
  return getJson<ReferralTransaction[]>(`/referral/users/${userId}/transactions`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function registerWithReferral(payload: RegisterWithReferralPayload): Promise<RegisterWithReferralResponse> {
  return postJson<RegisterWithReferralResponse>('/auth/register-with-referral', payload)
}
