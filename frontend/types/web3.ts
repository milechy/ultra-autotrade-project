// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.

export type SupportedChain = 'arbitrum' | 'arbitrum-sepolia' | 'base-sepolia' | 'base-sepolia'
export type SupportedToken = 'USDC' | 'USDT' | 'WETH' | 'WBTC' | 'DAI'
export type TransactionStatus = 'idle' | 'pending' | 'confirming' | 'success' | 'failed'
export type InterestRateMode = 1 | 2  // 1=stable, 2=variable

export interface WalletState {
  address: string | null
  chainId: number | null
  isConnected: boolean
  isCorrectChain: boolean
}

export interface AaveUserAccountData {
  totalCollateralBase: bigint     // USD, 8 decimals
  totalDebtBase: bigint           // USD, 8 decimals
  availableBorrowsBase: bigint    // USD, 8 decimals
  currentLiquidationThreshold: bigint  // bps, e.g. 8500 = 85%
  ltv: bigint                     // bps
  healthFactor: bigint            // 18 decimals (1e18 = 1.0)
}

export interface AaveUserReserveData {
  currentATokenBalance: bigint
  currentVariableDebt: bigint
  usageAsCollateral: boolean
}

export interface AaveReserveData {
  availableLiquidity: bigint
  totalVariableDebt: bigint
  liquidityRate: bigint
  variableBorrowRate: bigint
}

export interface MinimumBalanceCheck {
  isBelowMinimum: boolean
  currentValueUSD: number
  minimumUSD: number
  message: string
}
