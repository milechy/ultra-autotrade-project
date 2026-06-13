'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ExplanationData, ExplanationStep } from './types'

interface ReasonCardProps {
  explanation: ExplanationData
  className?: string
}

function StepItem({ step }: { step: ExplanationStep }) {
  const isConclusion = step.step === 1
  const isRisk = step.step === 4
  const isComparison = step.step === 5

  return (
    <div className="py-4 first:pt-0 last:pb-0">
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-bold">
          {step.step}
        </div>
        <div className="flex flex-col gap-1 flex-1">
          <p className="text-sm font-semibold text-muted-foreground">{step.title}</p>
          <p className={cn(isConclusion ? 'text-xl font-bold' : 'text-sm')}>
            {step.content}
          </p>
          {isRisk && step.risks && step.risks.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1">
              {step.risks.map((risk, i) => (
                <li key={i} className="flex gap-2 items-start">
                  <svg
                    className="h-4 w-4 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-sm">{risk}</span>
                </li>
              ))}
            </ul>
          )}
          {isComparison && step.comparison && (
            <p className="text-xs text-muted-foreground mt-1">{step.comparison}</p>
          )}
        </div>
      </div>
    </div>
  )
}

export function ReasonCard({ explanation, className }: ReasonCardProps) {
  const t = useTranslations('TransparencyReasonCard')
  if (!explanation || typeof explanation !== 'object') return null
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          {t('cardTitle', { action: explanation.action, confidence: explanation.confidence })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-border">
          {(explanation.steps ?? []).map((step) => (
            <StepItem key={step.step} step={step} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
