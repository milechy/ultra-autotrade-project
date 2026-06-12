'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { useBalance } from 'wagmi'
import { formatUnits } from 'viem'
import { useTranslations } from 'next-intl'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useWallet } from '@/hooks/useWallet'
import { getChainDisplayName } from '@/lib/web3/config'

export function WalletContent() {
  // injected / Privy embedded を統合した単一情報源（useWallet）から取得。
  const { address, isConnected, chainId, isCorrectChain, disconnect } = useWallet()
  const t = useTranslations('Wallet')
  const { data: balance } = useBalance({
    address: address ? (address as `0x${string}`) : undefined,
    chainId: chainId ?? undefined,
  })
  const chainName = getChainDisplayName(chainId)

  if (!isConnected) {
    return (
      <>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('stepsTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <Step num={1} text={t('step1')} />
            <Step num={2} text={t('step2')} />
            <Step num={3} text={t('step3')} />
          </CardContent>
        </Card>
        <div className="flex justify-center pt-2">
          <Button asChild size="sm">
            <Link href="/connect">{t('connectButton')}</Link>
          </Button>
        </div>
      </>
    )
  }

  return (
    <>
      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <span className="text-sm font-medium text-green-600">{t('connectedLabel')}</span>
          </div>
          <InfoRow
            label={t('addressLabel')}
            value={address ? `${address.slice(0, 6)}...${address.slice(-4)}` : '—'}
          />
          <InfoRow label={t('chainLabel')} value={chainName ?? '—'} />
          <InfoRow
            label={t('balanceLabel')}
            value={
              balance
                ? `${parseFloat(formatUnits(balance.value, balance.decimals)).toFixed(4)} ${balance.symbol}`
                : t('balanceLoading')
            }
          />
        </CardContent>
      </Card>

      {!isCorrectChain && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('wrongNetworkTitle')}</AlertTitle>
          <AlertDescription>
            {t('wrongNetworkDesc', { chain: chainName ?? t('balanceLoading') })}
          </AlertDescription>
        </Alert>
      )}

      {isCorrectChain && (
        <Button asChild className="w-full" size="lg">
          <Link href="/user/dashboard">{t('goToDashboard')}</Link>
        </Button>
      )}

      <div className="flex justify-center">
        <Button variant="outline" size="sm" onClick={() => disconnect()}>
          {t('disconnectButton')}
        </Button>
      </div>
    </>
  )
}

function Step({ num, text }: { num: number; text: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
        {num}
      </span>
      <span>{text}</span>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono font-medium">{value}</span>
    </div>
  )
}