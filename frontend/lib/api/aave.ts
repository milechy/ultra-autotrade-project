import { getJson } from "./http";

export interface AaveBalanceInfo {
  wallet_address: string;
  usdc_balance: string;   // Decimal serialized as string
  a_usdc_balance: string; // Decimal serialized as string
}

export interface AaveMonitorStatus {
  health_factor: string | null;
  balance: AaveBalanceInfo;
  client_type: string;
  fetched_at: string;
}

export async function fetchAaveStatus(token: string): Promise<AaveMonitorStatus> {
  return getJson<AaveMonitorStatus>("/api/aave/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}
