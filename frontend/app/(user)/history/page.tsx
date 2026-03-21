// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState, useMemo } from 'react'
import {
  StatsCards,
  TransactionFilters,
  TransactionList,
} from './_components'
import type { Transaction, OperationType } from './_components'

// TODO: Replace with GET /api/transactions?page=1&limit=50
const MOCK_TRANSACTIONS: Transaction[] = [
  {
    id: 'tx-001',
    type: 'SUPPLY',
    asset: 'USDC',
    amount: 1500,
    amountUSD: 1500,
    status: 'success',
    txHash: '0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
    chain: 'arbitrum',
    timestamp: '2026-03-21T10:30:00Z',
  },
  {
    id: 'tx-002',
    type: 'BORROW',
    asset: 'USDT',
    amount: 800,
    amountUSD: 800,
    status: 'success',
    txHash: '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
    chain: 'arbitrum',
    timestamp: '2026-03-21T08:15:00Z',
  },
  {
    id: 'tx-003',
    type: 'REPAY',
    asset: 'USDT',
    amount: 400,
    amountUSD: 400,
    status: 'success',
    txHash: '0x9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba',
    chain: 'arbitrum',
    timestamp: '2026-03-20T20:45:00Z',
  },
  {
    id: 'tx-004',
    type: 'SUPPLY',
    asset: 'WETH',
    amount: 0.5,
    amountUSD: 1650,
    status: 'success',
    txHash: '0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
    chain: 'arbitrum',
    timestamp: '2026-03-20T15:00:00Z',
  },
  {
    id: 'tx-005',
    type: 'WITHDRAW',
    asset: 'USDC',
    amount: 500,
    amountUSD: 500,
    status: 'success',
    txHash: '0xcafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe',
    chain: 'arbitrum',
    timestamp: '2026-03-20T11:30:00Z',
  },
  {
    id: 'tx-006',
    type: 'SUPPLY',
    asset: 'DAI',
    amount: 2000,
    amountUSD: 2000,
    status: 'pending',
    txHash: '0x1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff',
    chain: 'arbitrum',
    timestamp: '2026-03-19T18:20:00Z',
  },
  {
    id: 'tx-007',
    type: 'BORROW',
    asset: 'WBTC',
    amount: 0.02,
    amountUSD: 1200,
    status: 'failed',
    txHash: '0xffffeeeeddddccccbbbbaaaa0000999988887777666655554444333322221111',
    chain: 'arbitrum',
    timestamp: '2026-03-19T14:00:00Z',
  },
  {
    id: 'tx-008',
    type: 'REPAY',
    asset: 'USDC',
    amount: 300,
    amountUSD: 300,
    status: 'success',
    txHash: '0x2222333344445555666677778888999900001111aaaabbbbccccddddeeeeffff',
    chain: 'arbitrum',
    timestamp: '2026-03-18T09:10:00Z',
  },
  {
    id: 'tx-009',
    type: 'WITHDRAW',
    asset: 'WETH',
    amount: 0.3,
    amountUSD: 990,
    status: 'success',
    txHash: '0x3333444455556666777788889999000011112222aaaabbbbccccddddeeeeffff',
    chain: 'arbitrum',
    timestamp: '2026-03-17T22:00:00Z',
  },
  {
    id: 'tx-010',
    type: 'SUPPLY',
    asset: 'AAVE',
    amount: 10,
    amountUSD: 950,
    status: 'success',
    txHash: '0x4444555566667777888899990000111122223333aaaabbbbccccddddeeeeffff',
    chain: 'arbitrum',
    timestamp: '2026-03-16T13:45:00Z',
  },
  {
    id: 'tx-011',
    type: 'BORROW',
    asset: 'DAI',
    amount: 1000,
    amountUSD: 1000,
    status: 'success',
    txHash: '0x5555666677778888999900001111222233334444aaaabbbbccccddddeeeeffff',
    chain: 'arbitrum',
    timestamp: '2026-03-15T10:20:00Z',
  },
  {
    id: 'tx-012',
    type: 'REPAY',
    asset: 'DAI',
    amount: 600,
    amountUSD: 600,
    status: 'success',
    txHash: '0x6666777788889999000011112222333344445555aaaabbbbccccddddeeeeffff',
    chain: 'arbitrum',
    timestamp: '2026-03-14T07:55:00Z',
  },
]

export default function HistoryPage() {
  const [activeType, setActiveType] = useState<OperationType>('ALL')
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | 'all'>('all')

  // Compute stats from full mock list
  const totalCount = MOCK_TRANSACTIONS.length
  const totalProfitUSD = MOCK_TRANSACTIONS
    .filter((tx) => tx.status === 'success' && (tx.type === 'SUPPLY' || tx.type === 'BORROW'))
    .reduce((acc, tx) => acc + tx.amountUSD * 0.042 * (30 / 365), 0)
  const totalFeeUSD = MOCK_TRANSACTIONS
    .filter((tx) => tx.status === 'success')
    .reduce((acc) => acc + 0.15, 0)

  const filtered = useMemo(() => {
    let list = [...MOCK_TRANSACTIONS].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )

    if (activeType !== 'ALL') {
      list = list.filter((tx) => tx.type === activeType)
    }

    if (dateRange !== 'all') {
      const from = dateRange.from.getTime()
      const to = dateRange.to.getTime()
      list = list.filter((tx) => {
        const t = new Date(tx.timestamp).getTime()
        return t >= from && t <= to
      })
    }

    return list
  }, [activeType, dateRange])

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-xl font-bold text-zinc-100">取引履歴</h1>
          <p className="text-sm text-zinc-400 mt-0.5">Aave操作の全履歴を確認できます</p>
        </div>

        {/* Stats */}
        <StatsCards
          totalCount={totalCount}
          totalProfitUSD={totalProfitUSD}
          totalFeeUSD={totalFeeUSD}
        />

        {/* Filters */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <TransactionFilters
            activeType={activeType}
            onTypeChange={setActiveType}
            onDateRangeChange={setDateRange}
          />
        </div>

        {/* Transaction list */}
        <TransactionList transactions={filtered} />
      </div>
    </div>
  )
}
