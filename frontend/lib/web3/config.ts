// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

// Aave V3 コントラクトアドレス（チェーン別）
export const AAVE_V3_ADDRESSES = {
  arbitrum: {
    Pool: '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    PoolDataProvider: '0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654',
    Oracle: '0xb56c2F0B653B2e0b10C9b928C8580Ac5Df02C7C5',
  },
  'arbitrum-sepolia': {
    Pool: '0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff',
    PoolDataProvider: '0x7F23D86Ee20D869112572136221e173428DD523f',
    Oracle: '0x5Cd4628e6904807057A7eFe7C7Bc36a12B2d4ab5',
  },
  'base-sepolia': {
    Pool: '0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27',
    PoolDataProvider: '0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654',
    Oracle: '0xb56c2F0B653B2e0b10C9b928C8580Ac5Df02C7C5',
  },
} as const

// 対応トークンアドレス（チェーン別）
export const TOKEN_ADDRESSES = {
  arbitrum: {
    USDC: '0xaf88d065e77c8cC2239327C5EDb3A432268e5831',
    USDT: '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
    WETH: '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1',
    WBTC: '0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f',
    DAI:  '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
  },
  'arbitrum-sepolia': {
    USDC: '0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d',
    USDT: '0x27CEA6Eb8a21Aae05Eb29C91c5CA10592892F584',
    WETH: '0x980B62Da83eFf3D4576C647993b0c1D7faf17c73',
    WBTC: '0x6Bf14CB0A831078629D993FDeBcB182b21A8774C',
    DAI:  '0xc5E420e74Fd98Da91dAC7Bca77f00a6aECde02d4',
  },
  'base-sepolia': {
    USDC: '0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f',
    USDT: '0x27CEA6Eb8a21Aae05Eb29C91c5CA10592892F584',
    WETH: '0x4200000000000000000000000000000000000006',
    WBTC: '0x6Bf14CB0A831078629D993FDeBcB182b21A8774C',
    DAI:  '0xc5E420e74Fd98Da91dAC7Bca77f00a6aECde02d4',
  },
} as const

// チェーン定義
export const SUPPORTED_CHAINS = {
  arbitrum: {
    id: 42161,
    name: 'Arbitrum One',
    rpc: process.env.NEXT_PUBLIC_ARBITRUM_ONE_RPC || 'https://arb1.arbitrum.io/rpc',
  },
  'arbitrum-sepolia': {
    id: 421614,
    name: 'Arbitrum Sepolia',
    rpc: process.env.NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC || 'https://sepolia-rollup.arbitrum.io/rpc',
  },
  'base-sepolia': {
    id: 84532,
    name: 'Base Sepolia',
    rpc: process.env.NEXT_PUBLIC_BASE_SEPOLIA_RPC || 'https://sepolia.base.org',
  },
} as const

export type SupportedChainKey = keyof typeof SUPPORTED_CHAINS
export type SupportedToken = keyof typeof TOKEN_ADDRESSES.arbitrum

export const DEFAULT_CHAIN: SupportedChainKey =
  (process.env.NEXT_PUBLIC_DEFAULT_CHAIN as SupportedChainKey) || 'base-sepolia'

export const MINIMUM_USD_BALANCE = 3000
export const ARBITRUM_CHAIN_IDS = [42161, 421614, 84532]

export function getChainKey(chainId: number): SupportedChainKey | null {
  if (chainId === 42161) return 'arbitrum'
  if (chainId === 421614) return 'arbitrum-sepolia'
  if (chainId === 84532) return 'base-sepolia'
  return null
}
