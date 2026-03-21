'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

interface Position {
  asset: string
  supplied: number
  borrowed: number
  usdValue: number
}

interface UserPositionsProps {
  positions: Position[]
}

function formatAmount(value: number): string {
  if (value >= 1000) return value.toLocaleString('ja-JP', { maximumFractionDigits: 0 })
  return value.toLocaleString('ja-JP', { maximumFractionDigits: 4 })
}

function formatUSD(value: number): string {
  return '$' + value.toLocaleString('ja-JP', { maximumFractionDigits: 0 })
}

export function UserPositions({ positions }: UserPositionsProps) {
  if (positions.length === 0) {
    return (
      <div className="text-sm text-gray-500 py-3 text-center">ポジションなし</div>
    )
  }

  return (
    <div className="space-y-2">
      {positions.map((pos, i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-lg bg-gray-800/50 px-3 py-2"
        >
          <div className="flex items-center gap-3">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-blue-600/20 text-xs font-bold text-blue-400">
              {pos.asset.slice(0, 2)}
            </span>
            <span className="text-sm font-medium text-gray-100">{pos.asset}</span>
          </div>
          <div className="flex gap-4 text-right text-xs">
            <div>
              <div className="text-gray-500">Supply</div>
              <div className="font-mono text-green-400">{formatAmount(pos.supplied)}</div>
            </div>
            {pos.borrowed > 0 && (
              <div>
                <div className="text-gray-500">Borrow</div>
                <div className="font-mono text-red-400">{formatAmount(pos.borrowed)}</div>
              </div>
            )}
            <div>
              <div className="text-gray-500">USD</div>
              <div className="font-mono text-gray-200">{formatUSD(pos.usdValue)}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
