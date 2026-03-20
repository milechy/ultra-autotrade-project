'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useWeb3Modal } from '@web3modal/wagmi/react'
import { useAccount, useDisconnect } from 'wagmi'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

function truncateAddress(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`
}

export function ConnectWalletButton() {
  const { open } = useWeb3Modal()
  const { address, isConnected, chain } = useAccount()
  const { disconnect } = useDisconnect()

  if (isConnected && address) {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="text-xs">
          {chain?.name ?? 'Unknown'}
        </Badge>
        <Button
          variant="outline"
          size="sm"
          onClick={() => disconnect()}
        >
          {truncateAddress(address)}
        </Button>
      </div>
    )
  }

  return (
    <Button onClick={() => open()} size="sm">
      ウォレット接続
    </Button>
  )
}