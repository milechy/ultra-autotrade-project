'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'

interface Factor {
  score: number
  label: string
}

interface Factors {
  technical: Factor
  macro: Factor
  geopolitical: Factor
  sentiment: Factor
}

interface FactorAnalysisProps {
  factors: Factors
}

export function FactorAnalysis({ factors }: FactorAnalysisProps) {
  const t = useTranslations('Decisions')
  const entries = Object.entries(factors) as [keyof Factors, Factor][]

  const FACTOR_LABEL_KEYS: Record<keyof Factors, Parameters<typeof t>[0]> = {
    technical: 'factorTechnical',
    macro: 'factorMacro',
    geopolitical: 'factorGeopolitical',
    sentiment: 'factorSentiment',
  }

  return (
    <Card className="dark:bg-gray-900 dark:border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold text-gray-900 dark:text-gray-100">
          {t('factorAnalysisTitle')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {entries.map(([key, factor]) => {
          const isPositive = factor.score >= 0
          const barWidth = `${Math.abs(factor.score) * 100}%`

          return (
            <div key={key} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-700 dark:text-gray-300">
                  {t(FACTOR_LABEL_KEYS[key])}
                </span>
                <span
                  className={cn(
                    'text-xs font-medium',
                    isPositive
                      ? 'text-blue-600 dark:text-blue-400'
                      : 'text-red-600 dark:text-red-400',
                  )}
                >
                  {factor.label}
                </span>
              </div>
              {/* Centered bar: negative grows left, positive grows right */}
              <div className="relative h-2 w-full rounded-full bg-muted overflow-hidden">
                <div className="absolute inset-0 flex">
                  {/* Left half (negative) */}
                  <div className="w-1/2 flex justify-end overflow-hidden">
                    {!isPositive && (
                      <div
                        className="h-full rounded-l-full bg-red-500 dark:bg-red-600 transition-all duration-500"
                        style={{ width: barWidth }}
                      />
                    )}
                  </div>
                  {/* Center divider */}
                  <div className="w-px bg-gray-400 dark:bg-gray-600 flex-shrink-0" />
                  {/* Right half (positive) */}
                  <div className="w-1/2 flex justify-start overflow-hidden">
                    {isPositive && (
                      <div
                        className="h-full rounded-r-full bg-blue-500 dark:bg-blue-600 transition-all duration-500"
                        style={{ width: barWidth }}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
