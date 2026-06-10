'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { useBalance } from 'wagmi'
import { formatUnits } from 'viem'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useWallet } from '@/hooks/useWallet'
import { getChainDisplayName } from '@/lib/web3/config'

export function WalletContent() {
  // injected / Privy embedded を統合した単一情報源（useWallet）から取得。
  const { address, isConnected, chainId, isCorrectChain, disconnect } = useWallet()
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
            <CardTitle className="text-base">接続手順</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <Step num={1} text="MetaMask または WalletConnect 対応ウォレットを準備" />
            <Step num={2} text="Base メインネットを追加・切り替え" />
            <Step num={3} text="下のボタンからウォレットを接続" />
          </CardContent>
        </Card>
        <div className="flex justify-center pt-2">
          <Button asChild size="sm">
            <Link href="/connect">ウォレット接続</Link>
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
            <span className="text-sm font-medium text-green-600">接続済み</span>
          </div>
          <InfoRow
            label="アドレス"
            value={address ? `${address.slice(0, 6)}...${address.slice(-4)}` : '—'}
          />
          <InfoRow label="チェーン" value={chainName ?? '—'} />
          <InfoRow
            label="残高"
            value={
              balance
                ? `${parseFloat(formatUnits(balance.value, balance.decimals)).toFixed(4)} ${balance.symbol}`
                : '取得中...'
            }
          />
        </CardContent>
      </Card>

      {!isCorrectChain && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>ネットワークが違います</AlertTitle>
          <AlertDescription>
            Base メインネットに切り替えてください。現在: {chainName ?? '不明'}
          </AlertDescription>
        </Alert>
      )}

      {isCorrectChain && (
        <Button asChild className="w-full" size="lg">
          <Link href="/user/dashboard">ダッシュボードへ進む</Link>
        </Button>
      )}

      <div className="flex justify-center">
        <Button variant="outline" size="sm" onClick={() => disconnect()}>
          切断する
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