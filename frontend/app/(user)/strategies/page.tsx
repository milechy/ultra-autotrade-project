// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { TrendingUp, Layers, BarChart2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface Strategy {
  id: string
  icon: React.ElementType
  name: string
  subtitle: string
  description: string
  apyRange: string
  riskLevel: string
  riskColor: string
  status: 'active' | 'phase2'
  phase: string
}

const strategies: Strategy[] = [
  {
    id: 'aave-v3-usdc',
    icon: TrendingUp,
    name: 'Aave V3 USDC',
    subtitle: 'レンディング戦略',
    description: 'USDCをAave V3プロトコルに供給し、安定した貸出利息を獲得します。ヘルスファクター監視と自動リバランスで安全に運用します。',
    apyRange: '3〜5%',
    riskLevel: '低',
    riskColor: 'bg-green-500/20 text-green-400 border-green-500/30',
    status: 'active',
    phase: 'Phase 1',
  },
  {
    id: 'lido-steth',
    icon: Layers,
    name: 'Lido stETH',
    subtitle: 'リキッドステーキング',
    description: 'ETHをLidoプロトコルでリキッドステーキングし、stETHとして保有します。バリデーター報酬を受け取りながら流動性を維持できます。',
    apyRange: '3.5〜4%',
    riskLevel: '中',
    riskColor: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    status: 'phase2',
    phase: 'Phase 2',
  },
  {
    id: 'pendle-pt-yt',
    icon: BarChart2,
    name: 'Pendle PT/YT',
    subtitle: 'イールドトレーディング',
    description: 'Pendleプロトコルでトークン化された利回りを売買します。元本トークン（PT）と利回りトークン（YT）を活用した高度なイールド最適化戦略です。',
    apyRange: '5〜15%',
    riskLevel: '中〜高',
    riskColor: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    status: 'phase2',
    phase: 'Phase 2',
  },
]

function StatusBadge({ status, phase }: { status: Strategy['status']; phase: string }) {
  if (status === 'active') {
    return (
      <Badge className="border-green-500/30 bg-green-500/20 text-green-400">
        稼働中
      </Badge>
    )
  }
  return (
    <Badge className="border-yellow-500/30 bg-yellow-500/20 text-yellow-400">
      {phase}
    </Badge>
  )
}

function StrategyCard({ strategy }: { strategy: Strategy }) {
  const Icon = strategy.icon
  const isPhase2 = strategy.status === 'phase2'

  return (
    <div className="relative">
      <Card
        className={`border-zinc-800 bg-zinc-900 transition-colors ${
          isPhase2
            ? 'opacity-50 cursor-not-allowed'
            : 'hover:border-zinc-700 cursor-pointer'
        }`}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-3">
              <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-2">
                <Icon className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <CardTitle className="text-base text-zinc-100">{strategy.name}</CardTitle>
                <p className="text-xs text-zinc-500 mt-0.5">{strategy.subtitle}</p>
              </div>
            </div>
            <StatusBadge status={strategy.status} phase={strategy.phase} />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-zinc-400 leading-relaxed">{strategy.description}</p>

          <div className="flex items-center gap-4">
            <div>
              <p className="text-xs text-zinc-500">推定APY</p>
              <p className="text-sm font-semibold text-zinc-100">{strategy.apyRange}</p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">リスク</p>
              <Badge
                variant="outline"
                className={`text-xs mt-0.5 ${strategy.riskColor}`}
              >
                {strategy.riskLevel}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Coming Soon overlay for Phase 2 */}
      {isPhase2 && (
        <div className="absolute inset-0 flex items-center justify-center rounded-lg">
          <div className="rounded-full border border-zinc-700 bg-zinc-800/90 px-4 py-2 backdrop-blur-sm">
            <span className="text-sm font-semibold text-zinc-300">Coming Soon</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default function StrategiesPage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      {/* ヘッダー */}
      <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="px-4 py-3">
          <h1 className="text-lg font-semibold text-zinc-100">戦略選択</h1>
          <p className="text-xs text-zinc-500 mt-0.5">運用戦略を選択してください</p>
        </div>
      </div>

      <div className="px-4 py-4 pb-24 max-w-4xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {strategies.map((strategy) => (
            <StrategyCard key={strategy.id} strategy={strategy} />
          ))}
        </div>

        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs text-zinc-500">
            <span className="font-semibold text-zinc-400">Phase 2 予定:</span>{' '}
            Lido stETH・Pendle PT/YT戦略は現在開発中です。正式リリース後に選択可能になります。
          </p>
        </div>
      </div>
    </div>
  )
}
