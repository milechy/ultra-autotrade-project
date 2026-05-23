// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Supported asset abstraction. Phase 2 では複数アセットへ拡張する余地を残す。

export const SUPPORTED_ASSETS = ['USDC'] as const
export type SupportedAsset = (typeof SUPPORTED_ASSETS)[number]

export const ASSET_DECIMALS: Record<SupportedAsset, number> = {
  USDC: 6,
}
