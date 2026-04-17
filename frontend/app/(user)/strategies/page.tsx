// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useEffect, useState } from 'react'
import { TrendingUp, Layers, BarChart2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  fetchProtocolsHealth,
  fetchPendleMarkets,
  fetchLidoApr,
  type ProtocolHealth,
  type PendleMarketInfo,
  type LidoAprResponse,
} from '@/lib/api/protocols'

interface StrategyData {
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
  isOperational: boolean | null
  riskLevelApi: string | null
}

function buildStrategies(
  health: ProtocolHealth[],
  pendleMarkets: PendleMarketInfo[],
  lidoApr: LidoAprResponse | null
): StrategyData[] {
  const healthMap = Object.fromEntries(health.map((h) => [h.protocol, h]))

  const lidoHealth = healthMap['lido'] ?? null
  const pendleHealth = healthMap['pendle'] ?? null

  // Lido APY 文字列を生成
  let lidoApyRange = 'データなし'
  if (lidoApr) {
    const apr = Number(lidoApr.staking_apr).toFixed(1)
    lidoApyRange = `${apr}%`
  }

  // Pendle APY 文字列を生成（最初のマーケットの implied APY を使用）
  let pendleApyRange = 'データなし'
  if (pendleMarkets.length > 0) {
    const impliedApy = Number(pendleMarkets[0].implied_apy).toFixed(1)
    pendleApyRange = `${impliedApy}%（現在の想定利回り）`
  }

  return [
    {
      id: 'aave-v3-usdc',
      icon: TrendingUp,
      name: 'Aave V3 USDC',
      subtitle: 'レンディング戦略',
      description:
        'USDCをAave V3プロトコルに供給し、安定した貸出利息を獲得します。ヘルスファクター監視と自動リバランスで安全に運用します。',
      apyRange: '3〜5%',
      riskLevel: '低',
      riskColor: 'bg-green-500/20 text-green-400 border-green-500/30',
      status: 'active',
      phase: 'Phase 1',
      isOperational: healthMap['aave']?.is_operational ?? null,
      riskLevelApi: healthMap['aave']?.risk_level ?? null,
    },
    {
      id: 'lido-steth',
      icon: Layers,
      name: 'Lido stETH',
      subtitle: 'リキッドステーキング',
      description:
        'ETHをLidoプロトコルでリキッドステーキングし、stETHとして保有します。バリデーター報酬を受け取りながら流動性を維持できます。',
      apyRange: lidoApyRange,
      riskLevel: '中',
      riskColor: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
      status: 'phase2',
      phase: 'Phase 2',
      isOperational: lidoHealth?.is_operational ?? null,
      riskLevelApi: lidoHealth?.risk_level ?? null,
    },
    {
      id: 'pendle-pt-yt',
      icon: BarChart2,
      name: 'Pendle PT/YT',
      subtitle: 'イールドトレーディング',
      description:
        'Pendleプロトコルでトークン化された利回りを売買します。元本トークン（PT）と利回りトークン（YT）を活用した高度なイールド最適化戦略です。',
      apyRange: pendleApyRange,
      riskLevel: '中〜高',
      riskColor: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
      status: 'phase2',
      phase: 'Phase 2',
      isOperational: pendleHealth?.is_operational ?? null,
      riskLevelApi: pendleHealth?.risk_level ?? null,
    },
  ]
}

function StatusBadge({ status, phase }: { status: StrategyData['status']; phase: string }) {
  if (status === 'active') {
    return (
      <Badge className="border-green-500/30 bg-green-500/20 text-green-400">稼働中</Badge>
    )
  }
  return (
    <Badge className="border-yellow-500/30 bg-yellow-500/20 text-yellow-400">{phase}</Badge>
  )
}

function OperationalBadge({ isOperational }: { isOperational: boolean | null }) {
  if (isOperational === null) return null
  if (isOperational) {
    return (
      <span className="inline-block rounded-full bg-green-500/10 px-2 py-0.5 text-xs text-green-400">
        正常
      </span>
    )
  }
  return (
    <span className="inline-block rounded-full bg-red-500/10 px-2 py-0.5 text-xs text-red-400">
      異常
    </span>
  )
}

function StrategyCard({ strategy }: { strategy: StrategyData }) {
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
            <div className="flex flex-col items-end gap-1">
              <StatusBadge status={strategy.status} phase={strategy.phase} />
              <OperationalBadge isOperational={strategy.isOperational} />
            </div>
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
  const [strategies, setStrategies] = useState<StrategyData[]>(
    buildStrategies([], [], null)
  )
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [health, pendleMarkets, lidoApr] = await Promise.allSettled([
          fetchProtocolsHealth(),
          fetchPendleMarkets(),
          fetchLidoApr(),
        ])

        if (cancelled) return

        const healthData = health.status === 'fulfilled' ? health.value : []
        const pendleData = pendleMarkets.status === 'fulfilled' ? pendleMarkets.value : []
        const lidoData = lidoApr.status === 'fulfilled' ? lidoApr.value : null

        setStrategies(buildStrategies(healthData, pendleData, lidoData))
      } catch {
        // API 失敗時はデフォルト表示を維持
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

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
        {loading && (
          <p className="mb-4 text-xs text-zinc-500">プロトコル情報を取得中...</p>
        )}

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
