// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { usePathname } from 'next/navigation'
import { useLiff } from '@/hooks/useLiff'
import { useLiffAutoReAuth } from '@/hooks/useLiffAutoReAuth'
import { SessionExpiryBanner } from '@/components/SessionExpiryBanner'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'

// degrade ガードを適用しない経路。
// - liff-login : ログイン導線そのもの (未ログインで来る前提)
// - liff-sign-poc: 署名診断ページ (ログイン状態を意図的に表示する)
const AUTH_GUARD_EXEMPT = ['/liff-login', '/liff-sign-poc']

export default function LiffLayout({ children }: { children: React.ReactNode }) {
  const { isInitialized, isLoggedIn, error, liffConfigured } = useLiff()
  const pathname = usePathname()
  // ITP wipe で auth_token が消えた場合に、LINE 側 idToken を使って
  // 黙って /auth/line を叩き直し、ユーザー操作なしで session を復元する。
  // liff-login 以外の LIFF ページに直接遷移しても復帰できる。
  const reauth = useLiffAutoReAuth()

  // error 画面は「LIFF モードかつ実際の liff.init 失敗時」のみ表示する。
  // NEXT_PUBLIC_LIFF_ID 未設定（ブラウザ PWA モード）は error にせず、
  // 下の通常描画にフォールスルーして children をブラウザで表示する（degrade）。
  if (liffConfigured && error) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-red-400">LIFF初期化エラー: {error}</p>
      </div>
    )
  }

  if (!isInitialized) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-zinc-400">読み込み中...</p>
      </div>
    )
  }

  if (reauth.state === 'reauthing') {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-zinc-400">セッションを復元しています...</p>
      </div>
    )
  }

  // ── 中央集権 degrade ガード ──
  // 各 LIFF ページが個別に if(!isLoggedIn) 黒画面を持つ取りこぼしを解消し、ここで一元化する。
  // ブロックするのは「LIFF モード (liffConfigured=true) かつ LINE 未ログインかつ JWT も無い」場合のみ。
  // ブラウザ PWA モード (liffConfigured=false) は isLoggedIn が常に false でもブロックせず、
  // children を通常描画して degrade させる (ブラウザ承認導線はページ側で JWT を取得する)。
  // この構造により、新規 LIFF ページは個別ガードを書かなくても自動で degrade 対応になる。
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
  const isExempt = AUTH_GUARD_EXEMPT.includes(pathname ?? '')
  if (liffConfigured && !isLoggedIn && !token && !isExempt) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center px-4">
        <p className="text-zinc-400 text-sm">LINEアプリから開いてください</p>
      </div>
    )
  }

  return (
    <PrivyRootClient>
      <SessionExpiryBanner loginHref="/liff-login" />
      {children}
    </PrivyRootClient>
  )
}
