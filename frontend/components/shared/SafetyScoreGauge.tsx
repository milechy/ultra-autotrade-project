// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

export interface SafetyScoreGaugeProps {
  score: number
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
  className?: string
}

type ScoreKey = 'safe' | 'caution' | 'danger'

function getScoreConfig(score: number): { labelKey: ScoreKey; color: string; stroke: string; bg: string } {
  if (score >= 61)
    return { labelKey: 'safe', color: 'text-green-400', stroke: '#4ade80', bg: 'bg-green-500/10' }
  if (score >= 31)
    return { labelKey: 'caution', color: 'text-yellow-400', stroke: '#facc15', bg: 'bg-yellow-500/10' }
  return { labelKey: 'danger', color: 'text-red-400', stroke: '#f87171', bg: 'bg-red-500/10' }
}

const sizeConfig = {
  sm: { wh: 60, r: 26, strokeW: 5, textSize: 'text-sm' },
  md: { wh: 80, r: 36, strokeW: 7, textSize: 'text-lg' },
  lg: { wh: 100, r: 44, strokeW: 8, textSize: 'text-xl' },
} as const

/**
 * SafetyScoreGauge — 再利用可能な円形SVGゲージ
 *
 * Props:
 *   score     0–100 の安全スコア
 *   size      'sm' | 'md' | 'lg'  (default: 'md')
 *   showLabel ラベル（「安全」「注意」「危険」）を表示するか (default: true)
 */
export function SafetyScoreGauge({
  score,
  size = 'md',
  showLabel = true,
  className,
}: SafetyScoreGaugeProps) {
  const t = useTranslations('SharedSafetyScoreGauge')
  const clamped = Math.max(0, Math.min(100, Math.round(score)))
  const { labelKey, color, stroke, bg } = getScoreConfig(clamped)
  const { wh, r, strokeW, textSize } = sizeConfig[size]

  const circumference = 2 * Math.PI * r
  const dashOffset = circumference * (1 - clamped / 100)

  return (
    <div className={cn('flex items-center gap-3', className)}>
      {/* Circular gauge */}
      <div
        className={cn('relative flex items-center justify-center rounded-full flex-shrink-0', bg)}
        style={{ width: wh, height: wh }}
      >
        <svg
          width={wh}
          height={wh}
          viewBox={`0 0 ${wh} ${wh}`}
          className="absolute inset-0 -rotate-90"
        >
          <circle
            cx={wh / 2}
            cy={wh / 2}
            r={r}
            fill="none"
            stroke="#3f3f46"
            strokeWidth={strokeW}
          />
          <circle
            cx={wh / 2}
            cy={wh / 2}
            r={r}
            fill="none"
            stroke={stroke}
            strokeWidth={strokeW}
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
          />
        </svg>
        <span className={cn('relative font-bold', textSize, color)}>{clamped}</span>
      </div>

      {/* Label */}
      {showLabel && (
        <div>
          <p className={cn('font-bold', textSize, color)}>{t('scoreLabel', { score: clamped })}</p>
          <p className={cn('text-sm font-medium', color)}>{t(labelKey)}</p>
        </div>
      )}
    </div>
  )
}
