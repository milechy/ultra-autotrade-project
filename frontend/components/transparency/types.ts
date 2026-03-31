// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
export type WeatherSignal = 'sunny' | 'partly_cloudy' | 'cloudy' | 'stormy'

export interface SignalData {
  weather: WeatherSignal
  label: string
  description: string
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number  // 0-100
  updated_at?: string  // ISO8601
}

export interface MonthlyPnl {
  month: string  // "YYYY-MM"
  gain_jpy: number
  proposals: number
  win_rate: number
}

export interface SafetyBreakdownItem {
  name: string
  score: number  // 0-100
  weight: number  // 0-1
  description: string
}

export interface SafetyScoreData {
  total_score: number  // 0-100
  grade: 'A' | 'B' | 'C' | 'D' | 'F'
  breakdown: SafetyBreakdownItem[]
  summary: string
}

export interface PortfolioState {
  health_factor: number | null
  deposit_usd: number
  borrow_usd: number
  net_apy: number
  yield_annual_jpy: number
}

export interface ImpactData {
  action_type: string
  amount_usd: number
  before: PortfolioState
  after: PortfolioState
  diff_yield_annual_jpy: number
  metaphor: string
}

export interface ScenarioResult {
  scenario: string
  label: string
  probability: number  // 0-100
  yield_change_pct: number
  health_factor_change: number
  description: string
}

export interface SimulationData {
  scenarios: ScenarioResult[]
  best_scenario: string
  worst_scenario: string
  disclaimer: string
}

export interface ExplanationStep {
  step: number
  title: string
  content: string
  risks?: string[]
  comparison?: string
}

export interface ExplanationData {
  steps: ExplanationStep[]
  action: string
  confidence: number
}

export interface PerformanceData {
  total_proposals: number
  positive_results: number
  win_rate: number  // 0-100
  total_gain_jpy: number
  avg_gain_per_trade_jpy: number
  period_days: number
}

export interface RiskProfile {
  name: string
  name_ja: string
  description: string
  max_borrow_pct: number
  allowed_assets: string[]
  min_health_factor: number
}
