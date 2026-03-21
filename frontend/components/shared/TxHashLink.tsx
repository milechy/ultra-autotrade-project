'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { ExternalLink } from 'lucide-react'

export interface TxHashLinkProps {
  hash: string
  chain?: 'arbitrum' | 'base' | 'ethereum'
  truncate?: boolean
}

const explorerBaseUrl = {
  arbitrum: 'https://arbiscan.io/tx',
  base: 'https://basescan.org/tx',
  ethereum: 'https://etherscan.io/tx',
} as const

function truncateHash(hash: string): string {
  if (hash.length <= 12) return hash
  return `${hash.slice(0, 6)}...${hash.slice(-4)}`
}

export function TxHashLink({ hash, chain = 'arbitrum', truncate = true }: TxHashLinkProps) {
  const url = `${explorerBaseUrl[chain]}/${hash}`
  const display = truncate ? truncateHash(hash) : hash

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-mono text-sm underline-offset-4 hover:underline transition-colors"
    >
      {display}
      <ExternalLink className="h-3 w-3 flex-shrink-0" />
    </a>
  )
}
