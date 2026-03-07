import { getJson } from "./http";

export type ExchangeStatusResponse = {
  sandbox_mode: boolean;
  connected: boolean;
  balance_usdt: string | null;
  daily_trades_used: number;
  daily_trade_limit: number;
  last_trade_at: string | null;
};

export async function fetchExchangeStatus(token: string): Promise<ExchangeStatusResponse> {
  return await getJson<ExchangeStatusResponse>("/exchange/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}
