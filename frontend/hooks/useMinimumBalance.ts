// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback } from 'react'
import { MINIMUM_USD_BALANCE } from '@/lib/web3/config'
import type { AaveUserAccountData, MinimumBalanceCheck } from '@/types/web3'

const BASE_UNIT = 10 ** 8  // Aave oracle: USD value with 8 decimals

export function useMinimumBalance() {
  const checkMinimum = useCallback((accountData: AaveUserAccountData): MinimumBalanceCheck => {
    const currentValueUSD = Number(accountData.totalCollateralBase) / BASE_UNIT
    const isBelowMinimum = currentValueUSD < MINIMUM_USD_BALANCE

    return {
      isBelowMinimum,
      currentValueUSD,
      minimumUSD: MINIMUM_USD_BALANCE,
      message: isBelowMinimum
        ? `推奨運用額 $${MINIMUM_USD_BALANCE.toLocaleString()} USD を下回っています（現在: $${currentValueUSD.toFixed(2)}）`
        : `残高 $${currentValueUSD.toFixed(2)} USD は推奨運用額を満たしています`,
    }
  }, [])

  return { checkMinimum, minimumUSD: MINIMUM_USD_BALANCE }
}
