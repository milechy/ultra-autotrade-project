// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
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
  type RiskLevel,
} from '@/lib/api/protocols'

type RiskLevelKey = RiskLevel | 'medium_high'

interface StrategyData {
  id: string
  icon: React.ElementType
  name: string
  subtitleKey: 'aave' | 'lido' | 'pendle'
  descriptionKey: 'aave' | 'lido' | 'pendle'
  apyRange: string
  riskLevelKey: RiskLevelKey
  riskColor: string
  status: 'active' | 'phase2'
  phase: string
  isOperational: boolean | null
}

// risk_level を色クラスに変換する（label は useTranslations で解決）
function riskLevelToColor(level: RiskLevelKey): string {
  switch (level) {
    case 'low':
      return 'bg-green-500/20 text-green-400 border-green-500/30'
    case 'medium':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
    case 'high':
      return 'bg-orange-500/20 text-orange-400 border-orange-500/30'
    case 'critical':
      return 'bg-red-500/20 text-red-400 border-red-500/30'
    case 'medium_high':
      return 'bg-orange-500/20 text-orange-400 border-orange-500/30'
  }
}

function buildStrategies(
  health: ProtocolHealth[],
  pendleMarkets: PendleMarketInfo[],
  lidoApr: LidoAprResponse | null,
  noDataText: string,
  currentYieldText: string,
  aaveApyRange: string
): StrategyData[] {
  const healthMap = Object.fromEntries(health.map((h) => [h.protocol, h]))

  const lidoHealth = healthMap['lido'] ?? null
  const pendleHealth = healthMap['pendle'] ?? null

  // Lido APY 文字列を生成
  let lidoApyRange = noDataText
  if (lidoApr) {
    const apr = Number(lidoApr.staking_apr).toFixed(1)
    lidoApyRange = `${apr}%`
  }

  // Pendle APY 文字列を生成（最初のマーケットの implied APY を使用）
  let pendleApyRange = noDataText
  if (pendleMarkets.length > 0) {
    const impliedApy = Number(pendleMarkets[0].implied_apy).toFixed(1)
    pendleApyRange = `${impliedApy}%${currentYieldText}`
  }

  // API の risk_level が取得できた場合はその値を優先し、未取得時は静的フォールバックを使用する
  const aaveRiskKey: RiskLevelKey = healthMap['aave']?.risk_level ?? 'low'
  const lidoRiskKey: RiskLevelKey = lidoHealth?.risk_level ?? 'medium'
  const pendleRiskKey: RiskLevelKey = pendleHealth?.risk_level ?? 'medium_high'

  return [
    {
      id: 'aave-v3-usdc',
      icon: TrendingUp,
      name: 'Aave V3 USDC',
      subtitleKey: 'aave',
      descriptionKey: 'aave',
      apyRange: aaveApyRange,
      riskLevelKey: aaveRiskKey,
      riskColor: riskLevelToColor(aaveRiskKey),
      status: 'active',
      phase: 'Phase 1',
      isOperational: healthMap['aave']?.is_operational ?? null,
    },
    {
      id: 'lido-steth',
      icon: Layers,
      name: 'Lido stETH',
      subtitleKey: 'lido',
      descriptionKey: 'lido',
      apyRange: lidoApyRange,
      riskLevelKey: lidoRiskKey,
      riskColor: riskLevelToColor(lidoRiskKey),
      status: 'phase2',
      phase: 'Phase 2',
      isOperational: lidoHealth?.is_operational ?? null,
    },
    {
      id: 'pendle-pt-yt',
      icon: BarChart2,
      name: 'Pendle PT/YT',
      subtitleKey: 'pendle',
      descriptionKey: 'pendle',
      apyRange: pendleApyRange,
      riskLevelKey: pendleRiskKey,
      riskColor: riskLevelToColor(pendleRiskKey),
      status: 'phase2',
      phase: 'Phase 2',
      isOperational: pendleHealth?.is_operational ?? null,
    },
  ]
}

function StatusBadge({
  status,
  phase,
  activeLabel,
}: {
  status: StrategyData['status']
  phase: string
  activeLabel: string
}) {
  if (status === 'active') {
    return (
      <Badge className="border-green-500/30 bg-green-500/20 text-green-400">{activeLabel}</Badge>
    )
  }
  return (
    <Badge className="border-yellow-500/30 bg-yellow-500/20 text-yellow-400">{phase}</Badge>
  )
}

function OperationalBadge({
  isOperational,
  operationalLabel,
  abnormalLabel,
}: {
  isOperational: boolean | null
  operationalLabel: string
  abnormalLabel: string
}) {
  if (isOperational === null) return null
  if (isOperational) {
    return (
      <span className="inline-block rounded-full bg-green-500/10 px-2 py-0.5 text-xs text-green-400">
        {operationalLabel}
      </span>
    )
  }
  return (
    <span className="inline-block rounded-full bg-red-500/10 px-2 py-0.5 text-xs text-red-400">
      {abnormalLabel}
    </span>
  )
}

function StrategyCard({
  strategy,
  t,
}: {
  strategy: StrategyData
  t: ReturnType<typeof useTranslations<'Strategies'>>
}) {
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
                <p className="text-xs text-zinc-500 mt-0.5">{t(`${strategy.subtitleKey}.subtitle`)}</p>
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <StatusBadge
                status={strategy.status}
                phase={strategy.phase}
                activeLabel={t('active')}
              />
              <OperationalBadge
                isOperational={strategy.isOperational}
                operationalLabel={t('operational')}
                abnormalLabel={t('abnormal')}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-zinc-400 leading-relaxed">{t(`${strategy.descriptionKey}.description`)}</p>

          <div className="flex items-center gap-4">
            <div>
              <p className="text-xs text-zinc-500">{t('estimatedApy')}</p>
              <p className="text-sm font-semibold text-zinc-100">{strategy.apyRange}</p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">{t('risk')}</p>
              <Badge
                variant="outline"
                className={`text-xs mt-0.5 ${strategy.riskColor}`}
              >
                {t(`risk_${strategy.riskLevelKey}`)}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Coming Soon overlay for Phase 2 */}
      {isPhase2 && (
        <div className="absolute inset-0 flex items-center justify-center rounded-lg">
          <div className="rounded-full border border-zinc-700 bg-zinc-800/90 px-4 py-2 backdrop-blur-sm">
            <span className="text-sm font-semibold text-zinc-300">{t('comingSoon')}</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default function StrategiesPage() {
  const t = useTranslations('Strategies')
  const [strategies, setStrategies] = useState<StrategyData[]>(
    buildStrategies([], [], null, t('noData'), t('currentYield'), t('aave.apyRange'))
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

        setStrategies(buildStrategies(healthData, pendleData, lidoData, t('noData'), t('currentYield'), t('aave.apyRange')))
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
  }, [t])

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* ヘッダー */}
      <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="px-4 py-3">
          <h1 className="text-lg font-semibold text-zinc-100">{t('pageTitle')}</h1>
          <p className="text-xs text-zinc-500 mt-0.5">{t('pageSubtitle')}</p>
        </div>
      </div>

      <div className="px-4 py-4 pb-24 max-w-4xl mx-auto">
        {loading && (
          <p className="mb-4 text-xs text-zinc-500">{t('loading')}</p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {strategies.map((strategy) => (
            <StrategyCard key={strategy.id} strategy={strategy} t={t} />
          ))}
        </div>

        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs text-zinc-500">
            <span className="font-semibold text-zinc-400">{t('phase2Note')}</span>{' '}
            {t('phase2NoteText')}
          </p>
        </div>
      </div>
    </div>
  )
}
