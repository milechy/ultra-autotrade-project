'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'

const WalletContent = dynamic(
  () => import('./WalletContent').then((m) => ({ default: m.WalletContent })),
  { ssr: false }
)

// 2026-05-26 Lane H: メール / SNS ログイン経由の Privy 埋込ウォレットを demo 表示。
// 既存 WalletContent (外部 wallet 経路) はそのまま残し、上に並べる。
const PrivyEmbeddedWalletInfo = dynamic(
  () =>
    import('@/components/wallet/PrivyEmbeddedWalletInfo').then((m) => ({
      default: m.PrivyEmbeddedWalletInfo,
    })),
  { ssr: false }
)

export default function WalletPage() {
  const t = useTranslations('Wallet')
  return (
    <main className="px-4 py-6 max-w-md mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('pageTitle')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t('pageSubtitle')}
        </p>
      </div>
      <PrivyEmbeddedWalletInfo />
      <WalletContent />
    </main>
  )
}
