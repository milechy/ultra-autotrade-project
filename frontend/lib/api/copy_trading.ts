// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getJson, postJson, deleteJson, putJson } from './http'

export type RiskLevel = 'low' | 'medium' | 'high'

export type Strategy = {
  id: string
  name: string
  description: string
  risk_level: RiskLevel
  strategist_id: string
  is_public: boolean
  created_at: string
}

export type StrategyPerformance = {
  strategy_id: string
  win_rate: number
  sharpe_ratio: number
  total_pnl: string
  total_trades: number
  updated_at: string
}

export type StrategyWithPerformance = Strategy & {
  performance: StrategyPerformance | null
}

export type CopySubscription = {
  id: string
  strategy_id: string
  follower_id: string
  copy_ratio: number
  is_active: boolean
  created_at: string
}

export type CreateStrategyRequest = {
  name: string
  description: string
  risk_level: RiskLevel
}

export type SubscribeRequest = {
  follower_id: string
  copy_ratio: number
}

export type UpdateRatioRequest = {
  copy_ratio: number
}

export async function getStrategies(token: string): Promise<StrategyWithPerformance[]> {
  return getJson<StrategyWithPerformance[]>('/exchange/strategies', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function getStrategy(id: string, token: string): Promise<StrategyWithPerformance> {
  return getJson<StrategyWithPerformance>(`/exchange/strategies/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function createStrategy(body: CreateStrategyRequest, token: string): Promise<Strategy> {
  return postJson<Strategy>('/exchange/strategies', body, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function subscribeStrategy(
  strategyId: string,
  body: SubscribeRequest,
  token: string
): Promise<CopySubscription> {
  return postJson<CopySubscription>(`/exchange/strategies/${strategyId}/subscribe`, body, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function unsubscribeStrategy(strategyId: string, token: string): Promise<void> {
  return deleteJson(`/exchange/strategies/${strategyId}/subscribe`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function updateSubscriptionRatio(
  subscriptionId: string,
  body: UpdateRatioRequest,
  token: string
): Promise<CopySubscription> {
  return putJson<CopySubscription>(`/exchange/subscriptions/${subscriptionId}/ratio`, body, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function getSubscriptions(token: string): Promise<CopySubscription[]> {
  return getJson<CopySubscription[]>('/exchange/subscriptions', {
    headers: { Authorization: `Bearer ${token}` },
  })
}
