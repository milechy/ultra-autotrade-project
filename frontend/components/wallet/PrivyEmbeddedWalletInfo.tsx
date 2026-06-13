'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// 2026-05-26 Lane H: Privy 埋込ウォレット情報表示コンポーネント (frontend-only / demo)。
// メール / SNS ログイン → 自動生成された埋込ウォレットのアドレスとチェーンを表示。
// 資金操作は含まない (Lane H demo 目的)。

import { useTranslations } from 'next-intl'
import { usePrivy } from '@privy-io/react-auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Mail, KeyRound, LogOut, Loader2 } from 'lucide-react'
import { usePrivyEmbeddedWallet } from '@/hooks/usePrivyEmbeddedWallet'

const CHAIN_NAMES: Record<number, string> = {
  84532: 'Base Sepolia',
}

export function PrivyEmbeddedWalletInfo() {
  const t = useTranslations('WalletPrivyEmbeddedWallet')
  const { login, logout } = usePrivy()
  const state = usePrivyEmbeddedWallet()

  if (state.status === 'unconfigured') {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <KeyRound className="h-4 w-4" />
            {t('unconfiguredTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {t('unconfiguredMessage')}
          </p>
        </CardContent>
      </Card>
    )
  }

  if (state.status === 'initializing') {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('initializingTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {t('initializingMessage')}
          </p>
        </CardContent>
      </Card>
    )
  }

  if (state.status === 'unauthenticated') {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Mail className="h-4 w-4" />
            {t('unauthenticatedTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {t('unauthenticatedMessage')}
          </p>
          <Button onClick={login} className="w-full">
            {t('loginButton')}
          </Button>
          <p className="text-[11px] text-muted-foreground">
            {t('demoNotice')}
          </p>
        </CardContent>
      </Card>
    )
  }

  if (state.status === 'no-wallet') {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('noWalletTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {t('noWalletMessage')}
          </p>
          <Button variant="outline" onClick={logout} className="w-full">
            <LogOut className="mr-2 h-4 w-4" />
            {t('logoutButton')}
          </Button>
        </CardContent>
      </Card>
    )
  }

  // state.status === 'ready'
  const { address, chainId } = state
  const chainName =
    chainId != null && CHAIN_NAMES[chainId]
      ? CHAIN_NAMES[chainId]
      : chainId === 8453
      ? t('chainMainnet')
      : chainId != null
      ? `Chain ${chainId}`
      : t('chainUnknown')

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center justify-between">
          <span>{t('readyTitle')}</span>
          <Badge variant="secondary">Privy</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Row label={t('labelAddress')} value={address ?? '—'} mono />
        <Row label={t('labelChain')} value={chainName} />
        <p className="text-[11px] text-muted-foreground pt-1">
          {t('demoNotice')}
        </p>
        <Button variant="outline" size="sm" onClick={logout} className="w-full">
          <LogOut className="mr-2 h-4 w-4" />
          {t('logoutButton')}
        </Button>
      </CardContent>
    </Card>
  )
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span
        className={
          mono
            ? 'font-mono text-xs break-all text-right'
            : 'font-medium text-right'
        }
      >
        {value}
      </span>
    </div>
  )
}
