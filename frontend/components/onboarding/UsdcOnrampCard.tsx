// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useUsdcBalance } from '@/hooks/useUsdcBalance'
import { useUsdcOnramp } from '@/hooks/useUsdcOnramp'

/**
 * onboarding 用 USDC 入金カード。
 *
 * - 現在の USDC 残高 (Base) が `thresholdUsd` 未満のときに表示
 * - クリックで Privy useFundWallet (Base/USDC) を起動
 * - デフォルト入金額 `amountUsd` USD (default 250)
 * - 残高に応じて CTA 文言を切替:
 *     - 残高 0          : 「USDC X 相当を入金する」
 *     - 残高 < threshold : 「あと $Y 必要 / USDC X を入金する」
 * - 入金フロー中 (`isOnrampLoading`) はボタンを disabled にして loading 表示
 * - 完了 (`lastAmount > 0`) で 5 秒間 success バナーを表示
 */

const ONRAMP_THRESHOLD_USD = 200
const DEFAULT_ONRAMP_AMOUNT_USD = 250
const SUCCESS_FLASH_MS = 5_000

export interface UsdcOnrampCardProps {
  thresholdUsd?: number
  amountUsd?: number
}

export function UsdcOnrampCard({
  thresholdUsd = ONRAMP_THRESHOLD_USD,
  amountUsd = DEFAULT_ONRAMP_AMOUNT_USD,
}: UsdcOnrampCardProps) {
  const { balanceUsd, isLoading: isBalanceLoading } = useUsdcBalance()
  const {
    openOnramp,
    isLoading: isOnrampLoading,
    error,
    lastAmount,
  } = useUsdcOnramp({ defaultAmount: amountUsd })

  const [hasClicked, setHasClicked] = useState(false)
  const [showSuccess, setShowSuccess] = useState(false)

  // lastAmount が 0 → 正 に変化したら success flash を 5 秒間出す
  useEffect(() => {
    if (lastAmount > 0) {
      setShowSuccess(true)
      const id = setTimeout(() => setShowSuccess(false), SUCCESS_FLASH_MS)
      return () => clearTimeout(id)
    }
    return undefined
  }, [lastAmount])

  // 残高未取得 (初期 0n) で表示すると onramp 直後に消えてしまうので、
  // balance fetch 進行中 (isBalanceLoading && balanceUsd === 0) は非表示。
  if (isBalanceLoading && balanceUsd === 0 && !hasClicked) {
    return null
  }
  // 既に閾値以上だが、入金直後の success flash 中なら 5 秒だけ残す
  if (balanceUsd >= thresholdUsd && !showSuccess) {
    return null
  }

  const shortfall = Math.max(0, thresholdUsd - balanceUsd)
  const shortfallLabel = shortfall.toFixed(2)

  // CTA 文言を残高差額に応じて切替
  let ctaLabel: string
  if (isOnrampLoading) {
    ctaLabel = '入金画面を開いています...'
  } else if (balanceUsd <= 0) {
    ctaLabel = `USDC ${amountUsd} 相当を入金する`
  } else {
    // 部分残高あり: 「あと $Y 必要」を含めた文言
    ctaLabel = `あと $${shortfallLabel} 必要 / USDC ${amountUsd} を入金する`
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
          {balanceUsd > 0 && balanceUsd < thresholdUsd && (
            <p className="text-xs text-gray-700 mt-1">
              閾値まで: <span className="font-semibold">${shortfallLabel}</span>
            </p>
          )}
        </div>
        <Button
          onClick={handleClick}
          disabled={isOnrampLoading}
          className="w-full"
          size="sm"
          aria-busy={isOnrampLoading}
        >
          {isOnrampLoading && (
            <span
              className="inline-block h-3 w-3 mr-2 rounded-full border-2 border-white border-t-transparent animate-spin"
              aria-hidden="true"
            />
          )}
          {ctaLabel}
        </Button>
        {error && (
          <p className="text-xs text-red-600" role="alert">
            エラー: {error.message}
          </p>
        )}
        {showSuccess && (
          <div
            className="rounded-md border border-green-300 bg-green-50 px-3 py-2 text-xs text-green-800 transition-opacity"
            role="status"
          >
            <span className="font-semibold">入金成功</span>: $
            {lastAmount.toFixed(2)} 相当の USDC が反映されました。
          </div>
        )}
        {hasClicked && !isOnrampLoading && !error && !showSuccess && (
          <p className="text-xs text-gray-500">
            入金後、残高は数十秒以内に反映されます。
          </p>
        )}
      </CardContent>
    </Card>
  )
}
