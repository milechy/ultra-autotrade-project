'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { cn } from '@/lib/utils'

export interface AssetIconProps {
  symbol: string
  size?: 'sm' | 'md' | 'lg'
}

const tokenConfig: Record<string, { bg: string; text: string; label: string }> = {
  USDC: { bg: 'bg-blue-500', text: 'text-white', label: 'UC' },
  USDT: { bg: 'bg-green-500', text: 'text-white', label: 'UT' },
  ETH:  { bg: 'bg-purple-500', text: 'text-white', label: 'E' },
  WETH: { bg: 'bg-gray-500', text: 'text-white', label: 'WE' },
  WBTC: { bg: 'bg-orange-500', text: 'text-white', label: 'WB' },
  DAI:  { bg: 'bg-yellow-400', text: 'text-gray-900 dark:text-gray-100', label: 'D' },
  AAVE: { bg: 'bg-pink-500', text: 'text-white', label: 'AA' },
}

const sizeClasses = {
  sm: 'w-6 h-6 text-xs',
  md: 'w-8 h-8 text-sm',
  lg: 'w-12 h-12 text-base',
} as const

export function AssetIcon({ symbol, size = 'md' }: AssetIconProps) {
  const config = tokenConfig[symbol.toUpperCase()] ?? {
    bg: 'bg-gray-400',
    text: 'text-white',
    label: symbol.slice(0, 2).toUpperCase(),
  }

  return (
    <div
      className={cn(
        'rounded-full flex items-center justify-center font-bold flex-shrink-0',
        sizeClasses[size],
        config.bg,
        config.text
      )}
      title={symbol}
    >
      {config.label}
    </div>
  )
}
