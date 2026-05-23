// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Supported asset abstraction. Phase 2 では複数アセットへ拡張する余地を残す。

export const SUPPORTED_ASSETS = ['USDC'] as const
export type SupportedAsset = (typeof SUPPORTED_ASSETS)[number]

export const ASSET_DECIMALS: Record<SupportedAsset, number> = {
  USDC: 6,
}

/**
 * Base mainnet (chainId 8453) における ERC-20 contract address。
 *
 * TODO (Phase 2):
 *   - USDT, DAI, EURC など追加対応アセットを増やす際は SUPPORTED_ASSETS と
 *     ASSET_DECIMALS にも対応エントリを追加する。
 *   - L2 を Base 以外(Optimism / Arbitrum)へ拡張する場合は
 *     chainId -> address の二次元 map に拡張する。
 */
export const ASSET_ADDRESSES: Record<SupportedAsset, `0x${string}`> = {
  USDC: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
}
