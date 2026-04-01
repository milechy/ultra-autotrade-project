// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { WalletAddressMask } from '@/components/shared/WalletAddressMask'
import { useState } from 'react'
import { toast } from 'sonner'

interface WalletInfoCardProps {
  address: string | null
  chainId: number | null
  onDisconnect: () => void
}

function getNetworkName(chainId: number | null): string {
  if (chainId === null) return '不明'
  const names: Record<number, string> = {
    1: 'Ethereum',
    42161: 'Arbitrum One',
    421614: 'Arbitrum Sepolia',
    84532: 'Base Sepolia',
    137: 'Polygon',
    80001: 'Polygon Mumbai',
    10: 'Optimism',
    8453: 'Base',
  }
  return names[chainId] ?? `Chain ${chainId}`
}

function getNetworkBadgeClass(chainId: number | null): string {
  const colorMap: Record<number, string> = {
    1: 'bg-blue-900/40 text-blue-300 border-blue-700',
    42161: 'bg-sky-900/40 text-sky-300 border-sky-700',
    421614: 'bg-sky-900/40 text-sky-300 border-sky-700',
    84532: 'bg-indigo-900/40 text-indigo-300 border-indigo-700',
    137: 'bg-purple-900/40 text-purple-300 border-purple-700',
  }
  return colorMap[chainId ?? 0] ?? 'bg-zinc-800 text-zinc-400 border-zinc-700'
}

export function WalletInfoCard({ address, chainId, onDisconnect }: WalletInfoCardProps) {
  const router = useRouter()
  const [dialogOpen, setDialogOpen] = useState(false)

  const handleDisconnectConfirm = () => {
    onDisconnect()
    setDialogOpen(false)
    toast('ウォレットを切断しました')
    router.push('/')
  }

  return (
    <>
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-zinc-100">ウォレット</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {address ? (
            <>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">接続中のアドレス</span>
                  <WalletAddressMask address={address} chars={6} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">ネットワーク</span>
                  <Badge
                    variant="outline"
                    className={`text-xs ${getNetworkBadgeClass(chainId)}`}
                  >
                    {getNetworkName(chainId)}
                  </Badge>
                </div>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setDialogOpen(true)}
                className="w-full border-red-800 text-red-400 hover:bg-red-950/20 hover:text-red-300 hover:border-red-700"
              >
                切断する
              </Button>
            </>
          ) : (
            <p className="text-sm text-zinc-500">ウォレットが接続されていません</p>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <AlertDialogContent className="bg-zinc-900 border-zinc-800">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-zinc-100">ウォレットを切断しますか？</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              ウォレットとの接続を切断します。再度ご利用には再接続が必要です。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-zinc-800 border-zinc-700 text-zinc-100 hover:bg-zinc-700">
              キャンセル
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDisconnectConfirm}
              className="bg-red-700 hover:bg-red-800 text-white"
            >
              切断する
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
