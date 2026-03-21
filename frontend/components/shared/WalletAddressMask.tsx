'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { toast } from 'sonner'

export interface WalletAddressMaskProps {
  address: string
  chars?: number
}

function maskAddress(address: string, chars: number): string {
  if (address.length <= chars + 4) return address
  return `${address.slice(0, chars)}...${address.slice(-4)}`
}

export function WalletAddressMask({ address, chars = 6 }: WalletAddressMaskProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(address)
      setCopied(true)
      toast('アドレスをコピーしました')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('コピーに失敗しました')
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 font-mono text-sm text-muted-foreground hover:text-foreground transition-colors group cursor-pointer"
      title={address}
    >
      <span>{maskAddress(address, chars)}</span>
      {copied ? (
        <Check className="h-3 w-3 text-green-500 flex-shrink-0" />
      ) : (
        <Copy className="h-3 w-3 flex-shrink-0 opacity-50 group-hover:opacity-100 transition-opacity" />
      )}
    </button>
  )
}
