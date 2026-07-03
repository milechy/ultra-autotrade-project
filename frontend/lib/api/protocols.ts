// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getAuthToken } from "../auth/token-key";
import { getJson } from "./http";

// 2026-07-03 修正: fetchOracleStatus は require_viewer 保護下だが Authorization
// ヘッダーが付与されておらず、production を含む全環境で 401 になっていた
// （ブラウザ実機確認で検出。lib/api/aave.ts と同種のバグ）。
function authHeaders(): HeadersInit {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

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

export interface OracleAlert {
  asset: string;
  level: "OK" | "WARN" | "HARD_STOP";
  max_deviation_pct: string | null;
  chainlink_price: string | null;
  pyth_price: string | null;
  twap_price: string | null;
  detail: string | null;
  checked_at: string;
}

export interface OracleStatusResponse {
  alerts: OracleAlert[];
}

export async function fetchProtocolsHealth(): Promise<ProtocolHealth[]> {
  return getJson<ProtocolHealth[]>("/api/protocols/health");
}

export async function fetchOracleStatus(): Promise<OracleStatusResponse> {
  return getJson<OracleStatusResponse>("/api/aave/oracle-status", { headers: authHeaders() });
}

export async function fetchPendleMarkets(): Promise<PendleMarketInfo[]> {
  return getJson<PendleMarketInfo[]>("/api/protocols/pendle/markets");
}

export async function fetchLidoApr(): Promise<LidoAprResponse> {
  return getJson<LidoAprResponse>("/api/protocols/lido/apr");
}
