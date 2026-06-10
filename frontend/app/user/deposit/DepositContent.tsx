'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useCallback } from 'react'
import { useAccount, useReadContract } from 'wagmi'
import { useFundWallet } from '@privy-io/react-auth'
import { base, baseSepolia } from 'wagmi/chains'
import { formatUnits } from 'viem'
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
const DEPOSIT_GATE_USD = 200
const DEFAULT_ONRAMP_AMOUNT = '200'

function getChainForPrivy(chainId: number | undefined) {
  return chainId === 84532 ? baseSepolia : base
}

export function DepositContent() {
  const { address, isConnected, chain } = useAccount()
  const [isFunding, setIsFunding] = useState(false)
  const [fundError, setFundError] = useState<string | null>(null)

  const usdcAddress = chain?.id != null ? USDC_BY_CHAIN[chain.id] : undefined

  const { data: usdcBalanceRaw, refetch: refetchBalance, isLoading: balanceLoading } = useReadContract({
    address: usdcAddress,
    abi: ERC20_ABI,
    functionName: 'balanceOf',
    args: address ? [address] : undefined,
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
          chain: getChainForPrivy(chain?.id),
          amount: DEFAULT_ONRAMP_AMOUNT,
          asset: 'USDC',
        },
      })
    } catch (e) {
      if (e instanceof Error && !e.message.toLowerCase().includes('exit')) {
        setFundError('入金処理中にエラーが発生しました。もう一度お試しください。')
      }
    } finally {
      setIsFunding(false)
      void refetchBalance()
    }
  }, [address, chain, fundWallet, refetchBalance])

  if (!isConnected || !address) {
    return (
      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>ウォレット未接続</AlertTitle>
        <AlertDescription>
          入金するには先にウォレットを接続してください。
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      {/* Wallet info */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">接続中のウォレット</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">アドレス</span>
            <span className="font-mono font-medium">
              {address.slice(0, 6)}...{address.slice(-4)}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">ネットワーク</span>
            <Badge variant="outline" className="text-xs">
              {chain?.name ?? '不明'}
            </Badge>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">USDC残高</span>
            <div className="flex items-center gap-1.5">
              {balanceLoading ? (
                <span className="text-muted-foreground text-xs">取得中...</span>
              ) : (
                <span className={`font-mono font-semibold ${meetsDepositGate ? 'text-green-600' : 'text-amber-500'}`}>
                  {usdcAmount !== null ? `$${usdcAmount.toFixed(2)}` : '—'}
                </span>
              )}
              <button
                onClick={() => void refetchBalance()}
                className="text-muted-foreground hover:text-foreground transition-colors"
                aria-label="残高を更新"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* $200 deposit gate */}
      {!balanceLoading && (
        <>
          {meetsDepositGate ? (
            <Alert className="border-green-500/40 bg-green-950/20">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <AlertTitle className="text-green-500">入金確認済み</AlertTitle>
              <AlertDescription>
                USDC ${usdcAmount?.toFixed(2)} — 最低入金額 ${DEPOSIT_GATE_USD} を満たしています。
                AIによる自動運用が可能な状態です。
              </AlertDescription>
            </Alert>
          ) : (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>最低入金額を満たしていません</AlertTitle>
              <AlertDescription>
                自動運用を開始するには USDC で最低 ${DEPOSIT_GATE_USD} の入金が必要です。
                現在の残高: {usdcAmount !== null ? `$${usdcAmount.toFixed(2)}` : '—'}
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
          <CardTitle className="text-base">USDCを入金する</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            取引所（例: SBI VCトレード）やお持ちのウォレットから USDC を送金して入金できます。
            資産はサーバーには預けられず、あなたのウォレットに直接届きます。
          </p>
          <div className="rounded-lg bg-muted/50 px-3 py-2 text-xs text-muted-foreground space-y-1">
            <p>・入金先: あなた自身のウォレット（ノンカストディアル）</p>
            <p>・推奨金額: ${DEPOSIT_GATE_USD} USDC 以上</p>
            <p>・着金チェーン: {chain?.name ?? 'Base'}（別ネットワークの USDC も自動変換）</p>
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
                処理中...
              </>
            ) : (
              <>
                <ArrowDownToLine className="mr-2 h-4 w-4" />
                入金アドレスを表示
              </>
            )}
          </Button>
          {meetsDepositGate && (
            <Button variant="outline" className="w-full" size="sm" asChild>
              <a href="/user/dashboard" className="flex items-center gap-1.5">
                <ExternalLink className="h-3.5 w-3.5" />
                ダッシュボードへ
              </a>
            </Button>
          )}
        </CardContent>
      </Card>

      <p className="text-center text-xs text-muted-foreground px-4">
        入金はPrivyの入金アドレス経由で処理され、別チェーンの USDC は自動でブリッジされます。
        ネットワーク・ブリッジ手数料がかかる場合があります。
      </p>
    </div>
  )
}
