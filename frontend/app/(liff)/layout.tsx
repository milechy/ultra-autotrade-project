// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import '../arobix/theme.css'
import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { NextIntlClientProvider, useTranslations } from 'next-intl'
import { useLiff } from '@/hooks/useLiff'
import { useLiffAutoReAuth } from '@/hooks/useLiffAutoReAuth'
import { useLiffTermsGate } from '@/hooks/useLiffTermsGate'
import { SessionExpiryBanner } from '@/components/SessionExpiryBanner'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'
import { getAuthToken } from '@/lib/auth/token-key'
import jaMessages from '@/messages/ja.json'
import enMessages from '@/messages/en.json'

// degrade ガードを適用しない経路。
// - liff-login : ログイン導線そのもの (未ログインで来る前提)
// - liff-sign-poc: 署名診断ページ (ログイン状態を意図的に表示する)
const AUTH_GUARD_EXEMPT = ['/liff-login', '/liff-sign-poc']

// 重要事項同意 (terms_version="liff-v3") を入口非依存で強制する BtoC 消費者ページ。
// リッチメニュー / ブックマーク等で直接アクセスされても、未同意なら /liff-confirm へ
// 誘導する (法的同意の 1 経路依存を解消; Asana 1215360586206558)。
// パートナー承認系 (liff-approve / liff-fee-approve 等) は別系統のため対象外。
const TERMS_GATE_PATHS = ['/liff-chat']

// LiffLayoutLoading: layout レベルのローディング表示 (LiffIntlLayout の外側で使用するため
// inline Provider パターンを採用する)
function LiffLayoutLoadingInner() {
  const t = useTranslations('LiffLayout')
  return <p className="text-zinc-400">{t('reauthing')}</p>
}

function LiffLayoutLoading() {
  // NOTE: このコンポーネントは LiffIntlLayout の外側で使われる。
  // (liff)/layout.tsx は PrivyRootClient / LiffIntlLayout の親にあたるため
  // inline Provider で NextIntlClientProvider を自己完結させる。
  const messages = { LiffLayout: jaMessages.LiffLayout }
  return (
    <NextIntlClientProvider locale="ja" messages={messages}>
      <LiffLayoutLoadingInner />
    </NextIntlClientProvider>
  )
}

export default function LiffLayout({ children }: { children: React.ReactNode }) {
  const { isInitialized, isLoggedIn, error, liffConfigured } = useLiff()
  const pathname = usePathname()
  const router = useRouter()
  // ITP wipe で auth_token が消えた場合に、LINE 側 idToken を使って
  // 黙って /auth/line を叩き直し、ユーザー操作なしで session を復元する。
  // liff-login 以外の LIFF ページに直接遷移しても復帰できる。
  const reauth = useLiffAutoReAuth()

  // ── 重要事項同意ガード (入口非依存) ──
  // token を持つ消費者が TERMS_GATE_PATHS に直接来た場合に、liff-v3 未同意なら
  // /liff-confirm へ送る。token が無い場合は下の auth guard 側に委ねる。
  const token = getAuthToken()
  const needsTermsGate =
    !!token && TERMS_GATE_PATHS.some((p) => (pathname ?? '').startsWith(p))
  const termsState = useLiffTermsGate(needsTermsGate)
  useEffect(() => {
    if (needsTermsGate && termsState === 'not-accepted') {
      router.replace('/liff-confirm')
    }
  }, [needsTermsGate, termsState, router])

  // error 画面は「LIFF モードかつ実際の liff.init 失敗時」のみ表示する。
  // NEXT_PUBLIC_LIFF_ID 未設定（ブラウザ PWA モード）は error にせず、
  // 下の通常描画にフォールスルーして children をブラウザで表示する（degrade）。
  if (liffConfigured && error) {
    return (
      <div className="arobix-root">
        <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
          <p className="text-red-400">LIFF初期化エラー: {error}</p>
        </div>
      </div>
    )
  }

  if (!isInitialized) {
    return (
      <div className="arobix-root">
        <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
          <p className="text-zinc-400">読み込み中...</p>
        </div>
      </div>
    )
  }

  if (reauth.state === 'reauthing') {
    return (
      <div className="arobix-root">
        <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
          <LiffLayoutLoading />
        </div>
      </div>
    )
  }

  // ── 中央集権 degrade ガード ──
  // 各 LIFF ページが個別に if(!isLoggedIn) 黒画面を持つ取りこぼしを解消し、ここで一元化する。
  // ブロックするのは「LIFF モード (liffConfigured=true) かつ LINE 未ログインかつ JWT も無い」場合のみ。
  // ブラウザ PWA モード (liffConfigured=false) は isLoggedIn が常に false でもブロックせず、
  // children を通常描画して degrade させる (ブラウザ承認導線はページ側で JWT を取得する)。
  // この構造により、新規 LIFF ページは個別ガードを書かなくても自動で degrade 対応になる。
  const isExempt = AUTH_GUARD_EXEMPT.includes(pathname ?? '')
  if (liffConfigured && !isLoggedIn && !token && !isExempt) {
    return (
      <div className="arobix-root">
        <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center px-4">
          <p className="text-zinc-400 text-sm">LINEアプリから開いてください</p>
        </div>
      </div>
    )
  }

  // ブラウザ PWA モード (liffConfigured=false / v3) でトークンなし かつ要認証パス
  // → /liff-login (BrowserLoginPrompt / Privy) へ誘導する。
  const needsAuth = TERMS_GATE_PATHS.some((p) => (pathname ?? '').startsWith(p))
  if (!liffConfigured && !token && needsAuth && !isExempt) {
    router.replace('/liff-login')
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-zinc-400">読み込み中...</p>
      </div>
    )
  }

  // ── 重要事項同意ガード (render) ──
  // 同意未確定 (loading / not-accepted) の間は children を描画せず、上の useEffect が
  // /liff-confirm へ遷移するまで読み込み表示でブロックする (未同意ホームの一瞬の表示も防ぐ)。
  if (needsTermsGate && termsState !== 'accepted') {
    return (
      <div className="arobix-root">
        <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
          <p className="text-zinc-400">読み込み中...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="arobix-root">
      <PrivyRootClient>
        <SessionExpiryBanner loginHref="/liff-login" />
        {children}
      </PrivyRootClient>
    </div>
  )
}
