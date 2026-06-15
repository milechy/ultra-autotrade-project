'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/dashboard/RewardsCard.tsx

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Coins, Loader2, RefreshCw } from 'lucide-react'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import { claimRewards } from '@/lib/api/aave'
import type { RewardsResponse } from '@/lib/api/aave'

interface RewardsCardProps {
  /** admin ロールの場合のみ手動 Claim ボタンを表示する */
  isAdmin: boolean
}

export function RewardsCard({ isAdmin }: RewardsCardProps) {
  const t = useTranslations('RewardsCard')
  const { data, loading, error, refetch } = useAuthFetch<RewardsResponse>('/api/aave/rewards', {
    refreshInterval: 300000, // 5分ごとに自動更新
  })
  const [claiming, setClaiming] = useState(false)
  const [claimMessage, setClaimMessage] = useState<string | null>(null)

  const handleClaim = async () => {
    if (claiming) return
    setClaiming(true)
    setClaimMessage(null)
    try {
      const result = await claimRewards()
      if (result.claimed) {
        setClaimMessage(t('claimSuccess'))
      } else if (result.skip_reason) {
        setClaimMessage(t('claimSkipped', { reason: result.skip_reason }))
      } else if (result.error) {
        setClaimMessage(t('claimError', { error: result.error }))
      }
      void refetch()
    } catch (err) {
      setClaimMessage(t('claimError', { error: String(err) }))
    } finally {
      setClaiming(false)
    }
  }

  const totalUsd = data ? Number(data.total_usd) : 0

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Coins className="h-4 w-4 text-amber-500" />
          <h2 className="text-sm font-semibold text-zinc-400">{t('title')}</h2>
        </div>
        <button
          onClick={() => void refetch()}
          aria-label="更新"
          className="p-1 rounded hover:bg-zinc-800 transition-colors"
        >
          <RefreshCw className="h-3 w-3 text-zinc-500" />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-2">
          <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />
          <span className="text-xs text-zinc-500">{t('title')}...</span>
        </div>
      )}

      {!loading && error && (
        <p className="text-xs text-red-400 py-2">{t('fetchError')}</p>
      )}

      {!loading && !error && data && (
        <>
          {/* 合計 USD */}
          <div className="space-y-1">
            <p className="text-xs text-zinc-500">{t('unclaimedTotal')}</p>
            <p className="text-xl font-bold text-amber-400">
              ${totalUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>

          {/* トークン内訳 */}
          {data.rewards.length > 0 ? (
            <ul className="space-y-1">
              {data.rewards.map((r, i) => (
                <li key={i} className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400 font-medium">{r.asset_name}</span>
                  <span className="text-zinc-300">
                    {Number(r.amount).toFixed(4)}{' '}
                    <span className="text-zinc-500">(${Number(r.amount_usd).toFixed(2)})</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-zinc-500 py-1">{t('noData')}</p>
          )}

          <p className="text-[10px] text-zinc-600">{t('threshold')}</p>
        </>
      )}

      {/* admin のみ: 手動 Claim ボタン */}
      {isAdmin && (
        <button
          onClick={() => void handleClaim()}
          disabled={claiming}
          className="w-full rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-semibold py-2 transition-colors flex items-center justify-center gap-2"
        >
          {claiming ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              {t('claiming')}
            </>
          ) : (
            t('claimButton')
          )}
        </button>
      )}

      {claimMessage && (
        <p className="text-xs text-zinc-400 break-words">{claimMessage}</p>
      )}
    </div>
  )
}
