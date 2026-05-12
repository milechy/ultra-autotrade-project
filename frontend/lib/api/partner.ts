// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getJson } from './http'

export interface PartnerUserStats {
  user_id: number
  today_amount: string
  month_amount: string
  yesterday_return_pct: string | null
  month_return_pct: string | null
}

export function getPartnerUserStats(token: string, userId: number): Promise<PartnerUserStats> {
  return getJson<PartnerUserStats>(`/api/partner/users/${userId}/stats`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}
