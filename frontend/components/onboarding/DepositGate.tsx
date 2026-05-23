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

/**
 * 残高 < $200 のとき、子要素を覆って警告を表示する gate。
 * login / onboarding 以下は除外。
 */
export function DepositGate({ children }: DepositGateProps) {
  const pathname = usePathname()
  const { locked, balanceUsd, threshold, isLoading } = useDepositGate()

  if (shouldBypass(pathname)) {
    return <>{children}</>
  }

  if (isLoading) {
    return <>{children}</>
  }

  if (!locked) {
    return <>{children}</>
  }

  return (
    <div className="relative">
      <div className="pointer-events-none select-none opacity-30 blur-sm" aria-hidden>
        {children}
      </div>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="deposit-gate-title"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      >
        <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
          <h2 id="deposit-gate-title" className="text-lg font-bold text-gray-900">
            入金が必要です
          </h2>
          <p className="mt-3 text-sm text-gray-700">
            サービス開始には最低 ${threshold} の入金が必要です。
            <br />
            現在: ${balanceUsd.toFixed(2)}
          </p>
          <div className="mt-5 flex justify-end">
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
