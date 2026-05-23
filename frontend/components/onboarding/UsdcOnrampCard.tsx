// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useUsdcBalance } from '@/hooks/useUsdcBalance'
import { useUsdcOnramp } from '@/hooks/useUsdcOnramp'

/**
 * onboarding 用 USDC 入金カード。
 *
 * - 現在の USDC 残高 (Base) が $200 未満のときに表示
 * - クリックで Privy useFundWallet (Base/USDC) を起動
 * - デフォルト入金額 250 USD (後で UI で調整可)
 */

const ONRAMP_THRESHOLD_USD = 200
const DEFAULT_ONRAMP_AMOUNT_USD = 250

export interface UsdcOnrampCardProps {
  thresholdUsd?: number
  amountUsd?: number
}

export function UsdcOnrampCard({
  thresholdUsd = ONRAMP_THRESHOLD_USD,
  amountUsd = DEFAULT_ONRAMP_AMOUNT_USD,
}: UsdcOnrampCardProps) {
  const { balanceUsd, isLoading: isBalanceLoading } = useUsdcBalance()
  const { openOnramp, isLoading: isOnrampLoading, error } = useUsdcOnramp()
  const [hasClicked, setHasClicked] = useState(false)

  // 残高未取得 (初期 0n) で表示すると onramp 直後に消えてしまうので、
  // balance fetch 進行中 (isBalanceLoading && balanceUsd === 0) は非表示。
  if (isBalanceLoading && balanceUsd === 0) {
    return null
  }
  if (balanceUsd >= thresholdUsd) {
    return null
  }

  const handleClick = async () => {
    setHasClicked(true)
    try {
      await openOnramp({ amount: amountUsd })
    } catch {
      // error は useUsdcOnramp 内 state に保存される
    }
  }

  return (
    <Card className="border-dashed border-2 border-blue-300 bg-blue-50/40">
      <CardContent className="p-4 space-y-3">
        <div>
          <p className="text-sm font-semibold text-gray-900">
            運用を始めるには USDC が必要です
          </p>
          <p className="text-xs text-gray-600 mt-1">
            現在の残高: ${balanceUsd.toFixed(2)} (Base) /
            推奨: ${thresholdUsd} 以上
          </p>
        </div>
        <Button
          onClick={handleClick}
          disabled={isOnrampLoading}
          className="w-full"
          size="sm"
        >
          {isOnrampLoading
            ? '入金画面を開いています...'
            : `USDC ${amountUsd} 相当を入金する`}
        </Button>
        {error && (
          <p className="text-xs text-red-600">
            エラー: {error.message}
          </p>
        )}
        {hasClicked && !isOnrampLoading && !error && (
          <p className="text-xs text-gray-500">
            入金後、残高は数十秒以内に反映されます。
          </p>
        )}
      </CardContent>
    </Card>
  )
}
