// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import * as React from 'react'
import { usePathname } from 'next/navigation'
import { useDepositGate } from '@/hooks/useDepositGate'

type DepositGateProps = {
  children: React.ReactNode
}

// gate を適用しない pathname プレフィックス (login / onboarding は常に表示)
const BYPASS_PREFIXES = ['/login', '/onboarding', '/auth', '/register', '/r/']

function shouldBypass(pathname: string | null): boolean {
  if (!pathname) return false
  return BYPASS_PREFIXES.some((p) => pathname.startsWith(p))
}

function formatUsd(v: number): string {
  return v.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/**
 * 残高 < $200 のとき、子要素を覆って警告を表示する gate。
 * login / onboarding 以下は除外。
 */
export function DepositGate({ children }: DepositGateProps) {
  const pathname = usePathname()
  const { locked, balanceUsd, threshold, isLoading, error, refetch } = useDepositGate()

  if (shouldBypass(pathname)) {
    return <>{children}</>
  }

  // 初回ロード中は skeleton overlay。下層 UI へのフラッシュを抑える。
  if (isLoading) {
    return (
      <div className="relative">
        <div className="pointer-events-none select-none opacity-40" aria-hidden>
          {children}
        </div>
        <div
          role="status"
          aria-live="polite"
          aria-label="残高を確認しています"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
        >
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="flex items-center gap-3">
              <div
                className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent"
                aria-hidden
              />
              <p className="text-sm text-gray-700">残高を確認しています…</p>
            </div>
            <div className="mt-4 space-y-2">
              <div className="h-3 w-2/3 animate-pulse rounded bg-gray-200" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-gray-200" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  // 取得失敗 → 警告 + retry。安全側に倒して下層 UI は遮断しない。
  if (error) {
    return (
      <div className="relative">
        {children}
        <div
          role="alert"
          aria-live="assertive"
          className="fixed bottom-4 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 rounded-xl bg-red-50 p-4 shadow-lg ring-1 ring-red-200"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <p className="text-sm font-semibold text-red-900">残高の取得に失敗しました</p>
              <p className="mt-1 text-xs text-red-700">
                ネットワーク接続を確認のうえ再試行してください。
              </p>
            </div>
            <button
              type="button"
              onClick={refetch}
              className="inline-flex shrink-0 items-center rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
            >
              再試行
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!locked) {
    return <>{children}</>
  }

  const shortfall = Math.max(threshold - balanceUsd, 0)

  return (
    <div className="relative">
      <div className="pointer-events-none select-none opacity-30 blur-sm" aria-hidden>
        {children}
      </div>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="deposit-gate-title"
        aria-describedby="deposit-gate-desc"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      >
        <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
          <h2 id="deposit-gate-title" className="text-lg font-bold text-gray-900">
            入金が必要です
          </h2>
          <p id="deposit-gate-desc" className="mt-3 text-sm text-gray-700">
            サービス開始には最低 ${formatUsd(threshold)} の入金が必要です。
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-gray-50 p-3 text-sm">
            <div>
              <dt className="text-xs font-medium text-gray-500">現在の残高</dt>
              <dd className="mt-0.5 font-mono text-gray-900">${formatUsd(balanceUsd)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-gray-500">必要額</dt>
              <dd className="mt-0.5 font-mono text-gray-900">${formatUsd(threshold)}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-xs font-medium text-gray-500">不足分</dt>
              <dd className="mt-0.5 font-mono font-semibold text-red-600">
                ${formatUsd(shortfall)}
              </dd>
            </div>
          </dl>
          <div className="mt-5 flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={refetch}
              className="inline-flex items-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              残高を再確認
            </button>
            {/* TODO: P2-onramp の UsdcOnrampCard が merge されたら遷移先を差し替え */}
            <a
              href="/onboarding"
              className="inline-flex items-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
            >
              入金する
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DepositGate
