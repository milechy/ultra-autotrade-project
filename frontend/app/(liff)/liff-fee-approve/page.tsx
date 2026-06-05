'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-fee-approve/page.tsx
// URL: /liff-fee-approve
//
// F-S6 non-custodial: LIFF 内からアクセスする手数料 allowance 承認ページ

import { useLiff } from '@/hooks/useLiff'
import { FeeApproveCard } from '@/components/user/FeeApproveCard'
import { BrowserLoginPrompt } from '../_components/BrowserLoginPrompt'

export default function LiffFeeApprovePage() {
  const { isReady, error, liffConfigured } = useLiff()

  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <p className="text-zinc-400 text-sm">読み込み中...</p>
      </div>
    )
  }

  // error 画面は LIFF モードの実 init 失敗時のみ。ブラウザ degrade では error は立たない。
  if (liffConfigured && error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-red-400 text-sm text-center">
          LIFF初期化エラー: {error}
        </p>
      </div>
    )
  }

  // 黒画面の if(!isLoggedIn) ガードは (liff)/layout.tsx の中央集権 degrade ガードへ移譲済み。
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null

  if (!token) {
    // LIFF モード: LINE idToken から JWT を発行するため liff-login へ。
    if (liffConfigured) {
      if (typeof window !== 'undefined') {
        window.location.replace('/liff-login')
      }
      return (
        <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
          <p className="text-zinc-400 text-sm">再認証中...</p>
        </div>
      )
    }
    // ブラウザ degrade モード: Privy wallet 署名で JWT を取得する。
    return <BrowserLoginPrompt />
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
