// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/lib/api/portfolio.ts
//
// 統合ポートフォリオ API クライアント（消費者個人スコープ）。
// backend: GET /api/portfolio/unified（aave 純資産 + Privy wallet 残高 / CEX なし / fail-open）。

import { getJson } from "./http"

export interface SourceAllocation {
  source: string // "aave" | "wallet" | "cex"
  total_usd: string // Decimal 文字列
  allocation_pct: string // Decimal 文字列 (0-100)
  available: boolean
}

export interface UnifiedPortfolioView {
  grand_total_usd: string
  aave_net_usd: string
  wallet_usd: string
  cex_usd: string
  health_factor: string | null
  allocations: SourceAllocation[]
  sources_available: number
  sources_total: number
  degraded: boolean
}

export async function getUnifiedPortfolio(): Promise<UnifiedPortfolioView> {
  return getJson<UnifiedPortfolioView>("/api/portfolio/unified")
}
