'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/dashboard/IdleYieldCard.tsx
/**
 * IdleYieldCard — アイドル資本 Morpho Vaults 運用カード。
 *
 * 表示内容:
 *   - アイドル残高 (Bybit USDC free - Morpho 運用中)
 *   - 最高 APY Vault 情報
 *   - 運用中残高 / 獲得利息
 *   - 手動入金 / 引き出しボタン (admin ロールのみ)
 *
 * 設計:
 *   - 全テキストは ja.json から useTranslations で取得 (英語ハードコード禁止)
 *   - Privy API 障害時はデータなし表示 (fail-open)
 *   - 資金移動ボタンは isAdmin=true の場合のみ表示
 */

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { TrendingUp, Loader2, RefreshCw, AlertCircle } from 'lucide-react'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import {
  depositToVault,
  withdrawFromVault,
  type IdleCapitalReport,
  type VaultListResponse,
  type PositionListResponse,
} from '@/lib/api/yield'

interface IdleYieldCardProps {
  /** admin ロールの場合のみ入金/出金ボタンを表示する */
  isAdmin: boolean
}

export function IdleYieldCard({ isAdmin }: IdleYieldCardProps) {
  const t = useTranslations('IdleYieldCard')

  const { data: idleReport, loading: loadingIdle, error: errorIdle, refetch: refetchIdle } =
    useAuthFetch<IdleCapitalReport>('/api/yield-optimizer/idle-report', {
      refreshInterval: 300000, // 5分ごと
    })

  const { data: vaultData, loading: loadingVaults, error: errorVaults } =
    useAuthFetch<VaultListResponse>('/api/yield-optimizer/vaults', {
      refreshInterval: 300000,
    })

  const { data: positionData, loading: loadingPositions, refetch: refetchPositions } =
    useAuthFetch<PositionListResponse>('/api/yield-optimizer/positions', {
      refreshInterval: 300000,
    })

  const [depositAmount, setDepositAmount] = useState('')
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [vaultAddressInput, setVaultAddressInput] = useState('')
  const [submitting, setSubmitting] = useState<'deposit' | 'withdraw' | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const loading = loadingIdle || loadingVaults || loadingPositions
  const hasError = (errorIdle || errorVaults) && !idleReport && !vaultData

  const bestVault = vaultData?.best_apy_vault ?? null
  const totalDeposited = positionData?.total_deposited_usdc ?? '0'
  const totalEarned = positionData?.total_earned_usd ?? '0'
  const idleAmount = idleReport?.idle_amount ?? '0'
  const shouldDeploy = idleReport?.should_deploy ?? false

  const handleDeposit = async () => {
    if (submitting || !depositAmount || !vaultAddressInput) return
    setSubmitting('deposit')
    setActionMessage(null)
    try {
      const result = await depositToVault({
        vault_address: vaultAddressInput,
        amount_usdc: depositAmount,
      })
      setActionMessage(
        t('depositSuccess', { txHash: result.tx_hash.slice(0, 10) + '...' })
      )
      void refetchIdle()
      void refetchPositions()
      setDepositAmount('')
    } catch (err) {
      setActionMessage(t('depositError', { error: String(err) }))
    } finally {
      setSubmitting(null)
    }
  }

  const handleWithdraw = async () => {
    if (submitting || !withdrawAmount || !vaultAddressInput) return
    setSubmitting('withdraw')
    setActionMessage(null)
    try {
      const result = await withdrawFromVault({
        vault_address: vaultAddressInput,
        amount: withdrawAmount,
      })
      setActionMessage(
        t('withdrawSuccess', { txHash: result.tx_hash.slice(0, 10) + '...' })
      )
      void refetchIdle()
      void refetchPositions()
      setWithdrawAmount('')
    } catch (err) {
      setActionMessage(t('withdrawError', { error: String(err) }))
    } finally {
      setSubmitting(null)
    }
  }

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-emerald-500" />
          <h2 className="text-sm font-semibold text-zinc-400">{t('title')}</h2>
          {shouldDeploy && (
            <span className="inline-block rounded-full px-2 py-0.5 text-[10px] font-medium bg-emerald-500/20 text-emerald-400">
              {t('deployRecommended')}
            </span>
          )}
        </div>
        <button
          onClick={() => { void refetchIdle(); void refetchPositions() }}
          aria-label="更新"
          className="p-1 rounded hover:bg-zinc-800 transition-colors"
        >
          <RefreshCw className="h-3 w-3 text-zinc-500" />
        </button>
      </div>

      {/* ローディング */}
      {loading && (
        <div className="flex items-center gap-2 py-2">
          <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />
          <span className="text-xs text-zinc-500">{t('title')}...</span>
        </div>
      )}

      {/* エラー表示 */}
      {!loading && hasError && (
        <div className="flex items-center gap-2 py-2">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <p className="text-xs text-red-400">{t('fetchError')}</p>
        </div>
      )}

      {/* データ表示 */}
      {!loading && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
          {/* アイドル残高 */}
          <div>
            <dt className="text-xs text-zinc-500">{t('idleBalance')}</dt>
            <dd className="text-lg font-bold text-zinc-100">
              ${Number(idleAmount).toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </dd>
          </div>

          {/* 最高 APY */}
          <div>
            <dt className="text-xs text-zinc-500">{t('bestApy')}</dt>
            {bestVault ? (
              <dd className="text-lg font-bold text-emerald-400">
                {(Number(bestVault.apy) * 100).toFixed(2)}%
                <span className="ml-1 text-xs text-zinc-500 font-normal">{bestVault.name}</span>
              </dd>
            ) : (
              <dd className="text-sm text-zinc-500">{t('noVaults')}</dd>
            )}
          </div>

          {/* 運用中残高 */}
          <div>
            <dt className="text-xs text-zinc-500">{t('activePosition')}</dt>
            <dd className="text-sm font-semibold text-zinc-200">
              $
              {Number(totalDeposited).toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </dd>
          </div>

          {/* 獲得利息 */}
          <div>
            <dt className="text-xs text-zinc-500">{t('earnedInterest')}</dt>
            <dd className="text-sm font-semibold text-emerald-400">
              +$
              {Number(totalEarned).toFixed(2)}
            </dd>
          </div>
        </dl>
      )}

      {/* 閾値注記 */}
      {!loading && (
        <p className="text-[10px] text-zinc-600">{t('thresholdNote')}</p>
      )}

      {/* admin 専用: 入金 / 引き出しフォーム */}
      {isAdmin && !loading && (
        <div className="space-y-2 pt-2 border-t border-zinc-800">
          <input
            type="text"
            value={vaultAddressInput}
            onChange={(e) => setVaultAddressInput(e.target.value)}
            placeholder={t('vaultAddressPlaceholder')}
            className="w-full rounded-lg bg-zinc-800 text-xs text-zinc-200 px-3 py-2 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
          <div className="flex gap-2">
            {/* 入金 */}
            <div className="flex flex-1 gap-1">
              <input
                type="number"
                min="0"
                value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)}
                placeholder={t('amountPlaceholder')}
                className="flex-1 rounded-lg bg-zinc-800 text-xs text-zinc-200 px-3 py-2 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <button
                onClick={() => void handleDeposit()}
                disabled={submitting !== null || !depositAmount || !vaultAddressInput}
                className="rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold px-3 py-2 transition-colors flex items-center gap-1"
              >
                {submitting === 'deposit' ? (
                  <><Loader2 className="h-3 w-3 animate-spin" />{t('depositing')}</>
                ) : (
                  t('depositButton')
                )}
              </button>
            </div>

            {/* 引き出し */}
            <div className="flex flex-1 gap-1">
              <input
                type="number"
                min="0"
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                placeholder={t('amountPlaceholder')}
                className="flex-1 rounded-lg bg-zinc-800 text-xs text-zinc-200 px-3 py-2 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <button
                onClick={() => void handleWithdraw()}
                disabled={submitting !== null || !withdrawAmount || !vaultAddressInput}
                className="rounded-lg bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-white text-xs font-semibold px-3 py-2 transition-colors flex items-center gap-1"
              >
                {submitting === 'withdraw' ? (
                  <><Loader2 className="h-3 w-3 animate-spin" />{t('withdrawing')}</>
                ) : (
                  t('withdrawButton')
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* アクション結果メッセージ */}
      {actionMessage && (
        <p className="text-xs text-zinc-400 break-words">{actionMessage}</p>
      )}
    </div>
  )
}
