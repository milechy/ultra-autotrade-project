// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/aave.ts

import { getJson, postJson } from "./http";

export interface ClaimableReward {
  asset_name: string;
  reward_token_address: string;
  amount: string;
  amount_usd: string;
}

export interface RewardsResponse {
  rewards: ClaimableReward[];
  total_usd: string;
  fetched_at: string;
  note?: string;
}

export interface ClaimRewardsResponse {
  claimed: boolean;
  total_usd: string;
  rewards: ClaimableReward[];
  supply_tx_hash: string | null;
  skip_reason: string | null;
  error: string | null;
  claimed_at: string | null;
}

/**
 * GET /aave/rewards — 未請求リワードを取得する（viewer 以上）
 */
export async function getRewards(): Promise<RewardsResponse> {
  return getJson<RewardsResponse>("/api/aave/rewards");
}

/**
 * POST /aave/rewards/claim — リワードを手動 Claim する（admin のみ）
 */
export async function claimRewards(): Promise<ClaimRewardsResponse> {
  return postJson<ClaimRewardsResponse>("/api/aave/rewards/claim", {});
}
