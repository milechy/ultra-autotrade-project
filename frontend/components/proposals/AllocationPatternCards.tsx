// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { Shield, BarChart3, Rocket, Lock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * 運用先配分の 3 パターン提案 UI 枠。
 *
 * Base V3 で今日有効な運用先のみ執行可能にする方針 (Asana P0-4):
 *  - Conservative: Base V3 USDC supply のみ執行有効。
 *  - Standard / Aggressive: UI スケルトン + 無効化。Base 上の実在運用先で
 *    実際に異なる期待 APY / リスクを実 APY 値で示せるまで本実装しない。
 *
 * 背景(確定事実): wstETH / weETH は Base V3 に実在するが supply APY ほぼ 0%
 * (weETH は Disabled 表記)。USDC supply APY は約 3.4%。LST 利回りは保有値上がり
 * or 担保レバレッジで得るもので、単純 supply では Standard の差別化にならない。
 */

const PLACEHOLDER_NOTE = '現在有効な運用先が追加され次第、内容を更新します'

interface AllocationPattern {
  id: 'conservative' | 'standard' | 'aggressive'
  icon: React.ElementType
  name: string
  subtitle: string
  /** 執行有効なら本文。無効パターンでは undefined（スケルトン表示）。 */
  description?: string
  venue?: string
  apyLabel?: string
  riskLabel?: string
  riskColor?: string
  /** 執行可能か。false の場合は UI 枠のみで実行不可。 */
  enabled: boolean
}

const PATTERNS: AllocationPattern[] = [
  {
    id: 'conservative',
    icon: Shield,
    name: 'Conservative（保守）',
    subtitle: '安定供給戦略',
    description:
      'USDC を Base V3（Aave）に供給し、安定した貸出利息を獲得します。価格変動リスクを取らず、ヘルスファクター監視のもとで運用します。',
    venue: 'Base V3 USDC supply',
    apyLabel: '約 3.4%',
    riskLabel: '低',
    riskColor: 'bg-green-500/20 text-green-400 border-green-500/30',
    enabled: true,
  },
  {
    id: 'standard',
    icon: BarChart3,
    name: 'Standard（標準）',
    subtitle: '準備中',
    enabled: false,
  },
  {
    id: 'aggressive',
    icon: Rocket,
    name: 'Aggressive（積極）',
    subtitle: '準備中',
    enabled: false,
  },
]

function PatternCard({ pattern }: { pattern: AllocationPattern }) {
  const Icon = pattern.icon

  if (!pattern.enabled) {
    // Standard / Aggressive: UI スケルトン + 執行無効化
    return (
      <div className="relative" data-testid={`allocation-pattern-${pattern.id}`}>
        <Card className="border-zinc-800 bg-zinc-900 opacity-60">
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-3">
                <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-2">
                  <Icon className="h-5 w-5 text-zinc-500" />
                </div>
                <div>
                  <CardTitle className="text-base text-zinc-300">{pattern.name}</CardTitle>
                  <p className="mt-0.5 text-xs text-zinc-500">{pattern.subtitle}</p>
                </div>
              </div>
              <Badge className="border-zinc-600/40 bg-zinc-700/40 text-zinc-400">準備中</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* スケルトン行 */}
            <div className="space-y-2">
              <div className="h-3 w-3/4 rounded bg-zinc-800" />
              <div className="h-3 w-2/3 rounded bg-zinc-800" />
            </div>
            <p className="text-sm leading-relaxed text-zinc-500">{PLACEHOLDER_NOTE}</p>
            <button
              type="button"
              disabled
              aria-disabled="true"
              className="flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800/60 py-2 text-sm font-medium text-zinc-500"
            >
              <Lock className="h-4 w-4" />
              現在選択できません
            </button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Conservative: 執行有効
  return (
    <div className="relative" data-testid={`allocation-pattern-${pattern.id}`}>
      <Card className="border-emerald-700/50 bg-zinc-900 transition-colors hover:border-emerald-600">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-3">
              <div className="rounded-lg border border-emerald-700/50 bg-emerald-950/30 p-2">
                <Icon className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <CardTitle className="text-base text-zinc-100">{pattern.name}</CardTitle>
                <p className="mt-0.5 text-xs text-zinc-500">{pattern.subtitle}</p>
              </div>
            </div>
            <Badge className="border-green-500/30 bg-green-500/20 text-green-400">執行有効</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm leading-relaxed text-zinc-400">{pattern.description}</p>

          <div className="flex items-center gap-6">
            <div>
              <p className="text-xs text-zinc-500">運用先</p>
              <p className="mt-0.5 text-sm font-semibold text-zinc-100">{pattern.venue}</p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">推定APY</p>
              <p className="mt-0.5 text-sm font-semibold text-zinc-100">{pattern.apyLabel}</p>
            </div>
            <div>
              <p className="text-xs text-zinc-500">リスク</p>
              <Badge variant="outline" className={`mt-0.5 text-xs ${pattern.riskColor}`}>
                {pattern.riskLabel}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export function AllocationPatternCards() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {PATTERNS.map((pattern) => (
        <PatternCard key={pattern.id} pattern={pattern} />
      ))}
    </div>
  )
}

export default AllocationPatternCards
