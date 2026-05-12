'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { CheckCircle, Wallet, Network } from 'lucide-react'
import { usePrivy, useWallets } from '@privy-io/react-auth'
import { ethers } from 'ethers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { getStoredToken } from '@/lib/auth'
import { postJson } from '@/lib/api/http'
import type { HttpError } from '@/lib/api/http'

// 8453 = Base Mainnet, 84532 = Base Sepolia. build-time 埋め込み。
const DEFAULT_CHAIN_ID = parseInt(
  process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453',
  10,
)

const CHAIN_DISPLAY_NAMES: Record<number, string> = {
  84532: 'Base Sepolia',
  8453: 'Base メインネット',
}

function getNetworkDisplayName(chainId: number): string {
  return CHAIN_DISPLAY_NAMES[chainId] ?? `Chain ${chainId}`
}

// Privy returns chainId as "eip155:84532" or "84532".
function parsePrivyChainId(chainIdStr: string | undefined): number | null {
  if (!chainIdStr) return null
  const str = chainIdStr.includes(':') ? chainIdStr.split(':')[1] : chainIdStr
  const num = parseInt(str, 10)
  return isNaN(num) ? null : num
}

interface BackendWalletLinkResponse {
  user_id: number
  wallet_address: string
  linked_at: string
}

interface LinkedState {
  wallet_address: string
  network: string
}

function truncateAddress(addr: string): string {
  if (addr.length <= 10) return addr
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`
}

export function WalletConnectCard() {
  const token = getStoredToken()
  const { login, authenticated } = usePrivy()
  const { wallets } = useWallets()
  const wallet = wallets[0] ?? null

  const [linked, setLinked] = useState<LinkedState | null>(null)
  const [isLinking, setIsLinking] = useState(false)
  // Whether the user clicked "Connect wallet" and is waiting for Privy → sign → link.
  const pendingLinkRef = useRef(false)

  const linkWallet = useCallback(async () => {
    if (!token) {
      toast.error('認証されていません')
      return
    }
    if (!wallet) {
      // shouldn't happen because caller guards on wallet presence
      return
    }
    setIsLinking(true)
    try {
      const currentChainId = parsePrivyChainId(wallet.chainId)
      if (currentChainId !== DEFAULT_CHAIN_ID) {
        try {
          await wallet.switchChain(DEFAULT_CHAIN_ID)
        } catch {
          toast.error(
            `${getNetworkDisplayName(DEFAULT_CHAIN_ID)} への切替に失敗しました`,
          )
          return
        }
      }

      const address = wallet.address
      const timestamp = new Date().toISOString()
      const message = `Link wallet to Ultra AutoTrade\nAddress: ${address}\nTimestamp: ${timestamp}`

      const eip1193 = await wallet.getEthereumProvider()
      const ethProvider = new ethers.BrowserProvider(
        eip1193 as unknown as ethers.Eip1193Provider,
      )
      const signer = await ethProvider.getSigner()
      const signature = await signer.signMessage(message)

      const res = await postJson<BackendWalletLinkResponse>(
        '/auth/wallet/link',
        { address, signature, message },
        { headers: { Authorization: `Bearer ${token}` } },
      )
      setLinked({
        wallet_address: res.wallet_address,
        network: getNetworkDisplayName(DEFAULT_CHAIN_ID),
      })
    } catch (err: unknown) {
      const status = (err as HttpError)?.status
      if (status === 409) {
        toast.error('このウォレットは別アカウントで登録済みです')
      } else if (status === 422) {
        toast.error('署名検証に失敗しました')
      } else if (status === 401) {
        toast.error('認証セッションが切れました。再ログインしてください')
      } else {
        toast.error('ウォレットの接続に失敗しました')
      }
    } finally {
      setIsLinking(false)
      pendingLinkRef.current = false
    }
  }, [token, wallet])

  // If user clicked the button before Privy wallet was ready, resume once wallet appears.
  useEffect(() => {
    if (!pendingLinkRef.current) return
    if (!authenticated) return
    if (!wallet) return
    if (isLinking) return
    void linkWallet()
  }, [authenticated, wallet, isLinking, linkWallet])

  const handleConnect = useCallback(() => {
    if (!token) {
      toast.error('認証されていません')
      return
    }
    if (!authenticated || !wallet) {
      // Privy modal をまず開く。useEffect が wallets[0] 出現後に linkWallet() を呼ぶ。
      pendingLinkRef.current = true
      login()
      return
    }
    void linkWallet()
  }, [token, authenticated, wallet, login, linkWallet])

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
            <div className="flex items-center gap-1.5">
              <Network className="h-3 w-3 text-blue-400" />
              <span className="text-xs text-blue-400">{linked.network}</span>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">ウォレット未接続</p>
            <Button
              onClick={handleConnect}
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
