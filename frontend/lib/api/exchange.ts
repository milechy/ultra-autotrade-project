// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getJson, postJson } from "./http";

export type ExchangeStatusResponse = {
  sandbox_mode: boolean;
  connected: boolean;
  balance_usdt: string | null;
  daily_trades_used: number;
  daily_trade_limit: number;
  last_trade_at: string | null;
};

export type GridLevelResponse = {
  price: string;
  side: "buy" | "sell";
  order_id: string | null;
  filled: boolean;
};

export type GridStatusResponse = {
  enabled: boolean;
  symbol: string;
  upper_price: string;
  lower_price: string;
  grid_count: number;
  current_price: string | null;
  levels: GridLevelResponse[];
  total_orders: number;
  filled_orders: number;
  pnl_usd: string;
};

export type GridConfigRequest = {
  upper_price: string;
  lower_price: string;
  grid_count: number;
  symbol: string;
  amount_per_grid_usd: string;
  enabled: boolean;
  dry_run: boolean;
};

export async function fetchExchangeStatus(token: string): Promise<ExchangeStatusResponse> {
  return await getJson<ExchangeStatusResponse>("/exchange/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function executeGridBot(token: string, config: GridConfigRequest): Promise<GridStatusResponse> {
  return await postJson<GridStatusResponse>("/dca/grid/execute", config, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function fetchGridStatus(token: string): Promise<GridStatusResponse> {
  return await getJson<GridStatusResponse>("/dca/grid/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}
