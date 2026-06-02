'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-fee-approve/page.tsx
// URL: /liff-fee-approve
//
// F-S6 non-custodial: LIFF 内からアクセスする手数料 allowance 承認ページ

import { useLiff } from '@/hooks/useLiff'
import { FeeApproveCard } from '@/components/user/FeeApproveCard'

export default function LiffFeeApprovePage() {
  const { isReady, isLoggedIn, error } = useLiff()

  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <p className="text-zinc-400 text-sm">読み込み中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-red-400 text-sm text-center">
          LIFF初期化エラー: {error}
        </p>
      </div>
    )
  }

  if (!isLoggedIn) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-zinc-400 text-sm">LINEアプリから開いてください</p>
      </div>
    )
  }

  const token =
    typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null

  if (!token) {
    if (typeof window !== 'undefined') {
      window.location.replace('/liff-login')
    }
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-zinc-400 text-sm">再認証中...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold">手数料承認</h1>
        <p className="text-sm text-zinc-400 mt-1">
          月次手数料の自動徴収を有効にするための承認を行います
        </p>
      </div>
      <FeeApproveCard />
    </div>
  )
}
