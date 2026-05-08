'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { toast } from 'sonner'
import { CheckCircle, Wallet, Network } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { getStoredToken } from '@/lib/auth'
import { postJson } from '@/lib/api/http'
import type { HttpError } from '@/lib/api/http'

interface WalletLinkResponse {
  wallet_address: string
  network?: string
}

function truncateAddress(addr: string): string {
  if (addr.length <= 10) return addr
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`
}

export function WalletConnectCard() {
  const token = getStoredToken()
  const [linked, setLinked] = useState<WalletLinkResponse | null>(null)
  const [isLinking, setIsLinking] = useState(false)

  const handleConnect = async () => {
    if (!token) {
      toast.error('認証されていません')
      return
    }
    setIsLinking(true)
    try {
      const res = await postJson<WalletLinkResponse>(
        '/auth/wallet/link',
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      )
      setLinked(res)
    } catch (err: unknown) {
      const status = (err as HttpError)?.status
      if (status === 409) {
        toast.error('このウォレットは別アカウントで登録済みです')
      } else if (status === 422) {
        toast.error('署名検証に失敗しました')
      } else {
        toast.error('ウォレットの接続に失敗しました')
      }
    } finally {
      setIsLinking(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">ウォレット連携</CardTitle>
      </CardHeader>
      <CardContent>
        {linked ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
              <span className="text-sm text-emerald-400">接続済み:</span>
              <span className="font-mono text-sm">
                {truncateAddress(linked.wallet_address)}
              </span>
            </div>
            {linked.network && (
              <div className="flex items-center gap-1.5">
                <Network className="h-3 w-3 text-blue-400" />
                <span className="text-xs text-blue-400">{linked.network}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">ウォレット未接続</p>
            <Button
              onClick={() => { void handleConnect() }}
              disabled={isLinking}
              size="sm"
            >
              <Wallet className="h-4 w-4 mr-2" />
              {isLinking ? '接続中...' : 'ウォレット接続'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
