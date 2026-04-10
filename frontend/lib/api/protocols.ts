// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getJson } from "./http";

export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface ProtocolHealth {
  protocol: string;
  risk_level: RiskLevel;
  tvl_usd: string;
  tvl_change_24h_pct: string;
  is_operational: boolean;
  last_checked: string;
  alerts: string[];
}

export interface PendleMarketInfo {
  market_address: string;
  underlying_asset: string;
  maturity: string;
  days_to_maturity: number;
  implied_apy: string;
  pt_price: string;
  yt_price: string;
  tvl_usd: string;
}

export interface LidoAprResponse {
  staking_apr: string;
  source: string;
}

export async function fetchProtocolsHealth(): Promise<ProtocolHealth[]> {
  return getJson<ProtocolHealth[]>("/api/protocols/health");
}

export async function fetchPendleMarkets(): Promise<PendleMarketInfo[]> {
  return getJson<PendleMarketInfo[]>("/api/protocols/pendle/markets");
}

export async function fetchLidoApr(): Promise<LidoAprResponse> {
  return getJson<LidoAprResponse>("/api/protocols/lido/apr");
}
