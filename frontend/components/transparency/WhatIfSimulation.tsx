'use client'

import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SimulationData, ScenarioResult } from './types'

interface WhatIfSimulationProps {
  data: SimulationData
  className?: string
}

function ScenarioCard({ scenario, isBest }: { scenario: ScenarioResult; isBest: boolean }) {
  const changePositive = scenario.yield_change_pct >= 0

  return (
    <div
      className={cn(
        'rounded-lg border p-4 flex flex-col gap-2',
        isBest ? 'border-primary border-2' : 'border-border'
      )}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">{scenario.label}</p>
        {isBest && (
          <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold border-primary text-primary">
            ベスト
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{scenario.description}</p>
      <div className="flex flex-col gap-1 text-sm mt-1">
        <div className="flex justify-between">
          <span className="text-muted-foreground">収益変化</span>
          <span className={cn('font-medium', changePositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
            {changePositive ? '+' : ''}{(scenario.yield_change_pct ?? 0).toFixed(1)}%
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">確率</span>
          <span>{scenario.probability}%</span>
        </div>
      </div>
    </div>
  )
}

export function WhatIfSimulation({ data, className }: WhatIfSimulationProps) {
  if (!data) return null
  const scenarios = data.scenarios ?? []
  const colCount = scenarios.length

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">シナリオ分析</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          className={cn(
            'grid gap-3',
            colCount === 1 && 'grid-cols-1',
            colCount === 2 && 'grid-cols-1 md:grid-cols-2',
            colCount >= 3 && 'grid-cols-1 md:grid-cols-3'
          )}
        >
          {scenarios.map((scenario) => (
            <ScenarioCard
              key={scenario.scenario}
              scenario={scenario}
              isBest={scenario.scenario === data.best_scenario}
            />
          ))}
        </div>

        {/* Disclaimer */}
        <div className="rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-950 p-3 flex gap-2">
          <svg
            className="h-4 w-4 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.538-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="text-xs text-yellow-700 dark:text-yellow-300">{data.disclaimer}</p>
        </div>
      </CardContent>
    </Card>
  )
}
