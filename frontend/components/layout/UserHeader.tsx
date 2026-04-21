'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { useWallet } from '@/hooks/useWallet'
import { WalletAddressMask } from '@/components/shared'
import { useTranslations } from 'next-intl'
const CHAIN_INFO: Record<number, { name: string; colorClass: string }> = {
  84532: {
    name: 'Base Sepolia',
    colorClass: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
  },
  8453: {
    name: 'Base',
    colorClass: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  },
}

function NetworkBadge({ chainId, switchNetworkLabel }: { chainId: number | null; switchNetworkLabel: string }) {
  if (!chainId) return null

  const info = CHAIN_INFO[chainId]
  if (info) {
    return (
      <span
        className={`rounded-full border px-2 py-0.5 text-xs font-medium ${info.colorClass}`}
      >
        {info.name}
      </span>
    )
  }
  return (
    <span className="rounded-full border border-red-500/30 bg-red-500/20 px-2 py-0.5 text-xs font-medium text-red-400">
      {switchNetworkLabel}
    </span>
  )
}

export function UserHeader() {
  const { address, chainId, isConnected } = useWallet()
  const t = useTranslations('Header')

  return (
    <header className="sticky top-0 z-40 h-14 border-b border-zinc-800 bg-zinc-900/95 backdrop-blur-sm">
      <div className="flex h-full items-center justify-between px-4">
        {/* Logo */}
        <span className="text-sm font-bold text-white">{t('title')}</span>

        {/* Network badge */}
        <NetworkBadge chainId={chainId} switchNetworkLabel={t('switchNetwork')} />

        {/* Wallet */}
        {isConnected && address ? (
          <WalletAddressMask address={address} />
        ) : (
          <Link href="/connect" className="text-xs text-blue-400 hover:underline">{t('connectWallet')}</Link>
        )}
      </div>
    </header>
  )
}
