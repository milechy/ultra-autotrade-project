'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface SafetyScoreProps {
  score?: number
}

function getScoreConfig(score: number) {
  if (score >= 80) return { label: 'とても安全', color: 'text-green-400', stroke: '#4ade80', bg: 'bg-green-500/10' }
  if (score >= 50) return { label: '安全', color: 'text-yellow-400', stroke: '#facc15', bg: 'bg-yellow-500/10' }
  return { label: '注意', color: 'text-red-400', stroke: '#f87171', bg: 'bg-red-500/10' }
}

// TODO: Replace with GET /api/safety-score when backend endpoint is ready
const MOCK_SCORE = 85

export function SafetyScore({ score = MOCK_SCORE }: SafetyScoreProps) {
  const { label, color, stroke, bg } = getScoreConfig(score)
  const radius = 36
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference * (1 - score / 100)

  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-sm font-medium text-zinc-400">安全スコア</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="flex items-center gap-5">
          {/* Circular gauge */}
          <div className={`relative flex h-20 w-20 items-center justify-center rounded-full ${bg}`}>
            <svg width="80" height="80" viewBox="0 0 80 80" className="absolute inset-0 -rotate-90">
              <circle cx="40" cy="40" r={radius} fill="none" stroke="#3f3f46" strokeWidth="7" />
              <circle
                cx="40"
                cy="40"
                r={radius}
                fill="none"
                stroke={stroke}
                strokeWidth="7"
                strokeDasharray={circumference}
                strokeDashoffset={dashOffset}
                strokeLinecap="round"
              />
            </svg>
            <span className={`relative text-lg font-bold ${color}`}>{score}</span>
          </div>
          {/* Label */}
          <div>
            <p className={`text-xl font-bold ${color}`}>{score}点</p>
            <p className={`text-sm font-medium ${color}`}>{label}</p>
            <p className="text-xs text-zinc-500 mt-1">0〜100スコア</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
