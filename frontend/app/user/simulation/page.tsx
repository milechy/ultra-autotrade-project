'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { convertUSDCtoJPY, formatJPY } from '@/lib/jpy-converter'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Mock baseline balance used for USDC total projections
const BASELINE_USDC = 10000

interface ScenarioResult {
  name: string
  projected_gain_usd: string
  net_usd: string
}

interface SimulationApiResponse {
  scenarios: ScenarioResult[]
  best_scenario: string
  disclaimer: string
}

interface ScenarioCardData {
  name: string
  title: string
  badge: string
  badgeVariant: 'default' | 'secondary' | 'outline'
  projectedUSDC: number
  gainUSDC: number
  gainPct: number
  jpyAmount: number | null
}

const SCENARIO_META: Record<string, { title: string; badge: string; badgeVariant: 'default' | 'secondary' | 'outline' }> = {
  supply: {
    title: '今預けたら',
    badge: '供給',
    badgeVariant: 'default',
  },
  withdraw: {
    title: '全額引き出したら',
    badge: '引き出し',
    badgeVariant: 'secondary',
  },
  hold: {
    title: '何もしない',
    badge: 'ホールド',
    badgeVariant: 'outline',
  },
}

function ScenarioCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2 pt-4 px-4">
        <Skeleton className="h-5 w-32 rounded" />
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-2">
        <Skeleton className="h-8 w-40 rounded" />
        <Skeleton className="h-4 w-24 rounded" />
        <Skeleton className="h-4 w-20 rounded" />
      </CardContent>
    </Card>
  )
}

function ScenarioCard({ data }: { data: ScenarioCardData }) {
  const isPositive = data.gainUSDC >= 0
  const gainColor = isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
  const gainPrefix = isPositive ? '+' : ''

  return (
    <Card>
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">{data.title}</CardTitle>
          <Badge variant={data.badgeVariant}>{data.badge}</Badge>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-1">
        <p className="text-2xl font-bold">
          {data.projectedUSDC.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC
        </p>
        {data.jpyAmount !== null && (
          <p className="text-sm text-muted-foreground">
            ≈ {formatJPY(data.jpyAmount)}
          </p>
        )}
        <p className={`text-sm font-medium ${gainColor}`}>
          {gainPrefix}{data.gainUSDC.toFixed(4)} USDC ({gainPrefix}{data.gainPct.toFixed(2)}%)
        </p>
      </CardContent>
    </Card>
  )
}

function SimulationContent() {
  const [cards, setCards] = useState<ScenarioCardData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_URL}/api/transparency/simulation`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<SimulationApiResponse>
      })
      .then(async (data) => {
        const cardDataList = await Promise.all(
          data.scenarios.map(async (scenario) => {
            const meta = SCENARIO_META[scenario.name] ?? {
              title: scenario.name,
              badge: scenario.name,
              badgeVariant: 'outline' as const,
            }
            const gainUSDC = parseFloat(scenario.projected_gain_usd)
            const projectedUSDC = BASELINE_USDC + gainUSDC
            const gainPct = BASELINE_USDC > 0 ? (gainUSDC / BASELINE_USDC) * 100 : 0
            const jpyAmount = await convertUSDCtoJPY(projectedUSDC).catch(() => null)
            return {
              name: scenario.name,
              title: meta.title,
              badge: meta.badge,
              badgeVariant: meta.badgeVariant,
              projectedUSDC,
              gainUSDC,
              gainPct,
              jpyAmount,
            }
          })
        )
        // Ensure display order: supply, withdraw, hold
        const order = ['supply', 'withdraw', 'hold']
        cardDataList.sort(
          (a, b) => order.indexOf(a.name) - order.indexOf(b.name)
        )
        setCards(cardDataList)
      })
      .catch(() => {
        // Graceful fallback: use mock data
        const mockScenarios: Array<{ name: string; gainUSDC: number }> = [
          { name: 'supply', gainUSDC: 45.21 },
          { name: 'withdraw', gainUSDC: -2.0 },
          { name: 'hold', gainUSDC: 28.77 },
        ]
        const fallbackCards: ScenarioCardData[] = mockScenarios.map((s) => {
          const meta = SCENARIO_META[s.name]
          return {
            name: s.name,
            title: meta.title,
            badge: meta.badge,
            badgeVariant: meta.badgeVariant,
            projectedUSDC: BASELINE_USDC + s.gainUSDC,
            gainUSDC: s.gainUSDC,
            gainPct: (s.gainUSDC / BASELINE_USDC) * 100,
            jpyAmount: null, // no live rate in fallback
          }
        })
        setCards(fallbackCards)
        setError('シミュレーション中... (オフラインモード)')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="space-y-3">
        <ScenarioCardSkeleton />
        <ScenarioCardSkeleton />
        <ScenarioCardSkeleton />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {error && (
        <p className="text-xs text-yellow-600 dark:text-yellow-400 text-center py-1">
          {error}
        </p>
      )}

      {cards.map((card) => (
        <ScenarioCard key={card.name} data={card} />
      ))}

      <p className="text-xs text-muted-foreground text-center pt-2">
        ⚠️ この予測は保証ではありません。市場状況により実際の結果は異なります。
      </p>
    </div>
  )
}

export default function SimulationPage() {
  return (
    <main className="px-4 py-6 max-w-md mx-auto">
      <div className="mb-4">
        <h1 className="text-2xl font-bold">シミュレーション</h1>
        <p className="text-xs text-muted-foreground mt-1">30日後の予測シナリオ</p>
      </div>
      <ErrorBoundary>
        <SimulationContent />
      </ErrorBoundary>
    </main>
  )
}
