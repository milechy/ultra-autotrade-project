'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useCallback } from 'react'
import { useReadContract } from 'wagmi'
import { useFundWallet } from '@privy-io/react-auth'
import { base, baseSepolia } from 'wagmi/chains'
import { formatUnits } from 'viem'
import { useTranslations } from 'next-intl'
import { useWallet } from '@/hooks/useWallet'
import { getChainDisplayName, DEPOSIT_GATE_USD } from '@/lib/web3/config'
import {
  AlertTriangle,
  CheckCircle2,
  ArrowDownToLine,
  RefreshCw,
  ExternalLink,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { ERC20_ABI } from '@/lib/web3/abi/erc20'

// USDC contract addresses by chain ID
const USDC_BY_CHAIN: Record<number, `0x${string}`> = {
  8453: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',  // Base Mainnet
  84532: '0x036CbD53842c5426634e7929541eC2318f3dCF7e', // Base Sepolia
}

const USDC_DECIMALS = 6
// 入金ゲートは lib/web3/config.ts の DEPOSIT_GATE_USD を単一の真実源として参照する。
const DEFAULT_ONRAMP_AMOUNT = String(DEPOSIT_GATE_USD)

function getChainForPrivy(chainId: number | undefined) {
  return chainId === 84532 ? baseSepolia : base
}

export function DepositContent() {
  // injected / Privy embedded を統合した単一情報源（useWallet）から取得。
  const { address, isConnected, chainId } = useWallet()
  const t = useTranslations('Deposit')
  const [isFunding, setIsFunding] = useState(false)
  const [fundError, setFundError] = useState<string | null>(null)

  const chainName = getChainDisplayName(chainId)
  const usdcAddress = chainId != null ? USDC_BY_CHAIN[chainId] : undefined

  const { data: usdcBalanceRaw, refetch: refetchBalance, isLoading: balanceLoading } = useReadContract({
    address: usdcAddress,
    abi: ERC20_ABI,
    functionName: 'balanceOf',
    args: address ? [address as `0x${string}`] : undefined,
    chainId: chainId ?? undefined,
    query: { enabled: !!address && !!usdcAddress },
  })

  const { fundWallet } = useFundWallet({
    onUserExited: () => {
      setIsFunding(false)
      void refetchBalance()
    },
  })

  const usdcAmount = usdcBalanceRaw != null
    ? parseFloat(formatUnits(usdcBalanceRaw as bigint, USDC_DECIMALS))
    : null

  const meetsDepositGate = usdcAmount !== null && usdcAmount >= DEPOSIT_GATE_USD

  const handleFundWallet = useCallback(async () => {
    if (!address) return
    setIsFunding(true)
    setFundError(null)
    try {
      await fundWallet({
        address,
        options: {
          chain: getChainForPrivy(chainId ?? undefined),
          amount: DEFAULT_ONRAMP_AMOUNT,
          asset: 'USDC',
        },
      })
    } catch (e) {
      if (e instanceof Error && !e.message.toLowerCase().includes('exit')) {
        setFundError(t('fundError'))
      }
    } finally {
      setIsFunding(false)
      void refetchBalance()
    }
  }, [address, chainId, fundWallet, refetchBalance])

  if (!isConnected || !address) {
    return (
      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>{t('walletNotConnectedTitle')}</AlertTitle>
        <AlertDescription>
          {t('walletNotConnectedDesc')}
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      {/* Wallet info */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{t('connectedWalletTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{t('addressLabel')}</span>
            <span className="font-mono font-medium">
              {address.slice(0, 6)}...{address.slice(-4)}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{t('networkLabel')}</span>
            <Badge variant="outline" className="text-xs">
              {chainName ?? t('networkUnknown')}
            </Badge>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{t('usdcBalanceLabel')}</span>
            <div className="flex items-center gap-1.5">
              {balanceLoading ? (
                <span className="text-muted-foreground text-xs">{t('balanceLoading')}</span>
              ) : (
                <span className={`font-mono font-semibold ${meetsDepositGate ? 'text-green-600' : 'text-amber-500'}`}>
                  {usdcAmount !== null ? `$${usdcAmount.toFixed(2)}` : '—'}
                </span>
              )}
              <button
                onClick={() => void refetchBalance()}
                className="text-muted-foreground hover:text-foreground transition-colors"
                aria-label={t('refreshAriaLabel')}
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* $1,000 deposit gate */}
      {!balanceLoading && (
        <>
          {meetsDepositGate ? (
            <Alert className="border-green-500/40 bg-green-950/20">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <AlertTitle className="text-green-500">{t('depositConfirmedTitle')}</AlertTitle>
              <AlertDescription>
                {t('depositConfirmedDesc', { amount: usdcAmount?.toFixed(2) ?? '—', gate: String(DEPOSIT_GATE_USD) })}
              </AlertDescription>
            </Alert>
          ) : (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('depositGateFailTitle')}</AlertTitle>
              <AlertDescription>
                {t('depositGateFailDesc', { gate: String(DEPOSIT_GATE_USD), balance: usdcAmount !== null ? `$${usdcAmount.toFixed(2)}` : '—' })}
              </AlertDescription>
            </Alert>
          )}
        </>
      )}

      {/* Error message */}
      {fundError && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{fundError}</AlertDescription>
        </Alert>
      )}

      {/* Fund wallet CTA */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('fundCardTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {t('fundDesc')}
          </p>
          <div className="rounded-lg bg-muted/50 px-3 py-2 text-xs text-muted-foreground space-y-1">
            <p>・{t('fundBullet1')}</p>
            <p>・{t('fundBullet2', { gate: String(DEPOSIT_GATE_USD) })}</p>
            <p>・{t('fundBullet3', { chain: chainName ?? 'Base' })}</p>
          </div>
          <Button
            className="w-full"
            size="lg"
            onClick={() => void handleFundWallet()}
            disabled={isFunding}
          >
            {isFunding ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                {t('processingButton')}
              </>
            ) : (
              <>
                <ArrowDownToLine className="mr-2 h-4 w-4" />
                {t('showAddressButton')}
              </>
            )}
          </Button>
          {meetsDepositGate && (
            <Button variant="outline" className="w-full" size="sm" asChild>
              <a href="/user/dashboard" className="flex items-center gap-1.5">
                <ExternalLink className="h-3.5 w-3.5" />
                {t('goToDashboard')}
              </a>
            </Button>
          )}
        </CardContent>
      </Card>

      <p className="text-center text-xs text-muted-foreground px-4">
        {t('footerNote')}
      </p>
    </div>
  )
}
