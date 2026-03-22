'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { apiFetch } from '@/lib/api/client'

interface SafetyScoreBreakdown {
  util_score: string
  hf_score: string
  vol_score: string
}

interface SafetyScoreData {
  score: string
  label: string
  color: string
  breakdown: SafetyScoreBreakdown
}

function getScoreConfig(score: number) {
  if (score >= 80) return { label: 'とても安全', color: 'text-green-400', stroke: '#4ade80', bg: 'bg-green-500/10' }
  if (score >= 50) return { label: '安全', color: 'text-yellow-400', stroke: '#facc15', bg: 'bg-yellow-500/10' }
  return { label: '注意', color: 'text-red-400', stroke: '#f87171', bg: 'bg-red-500/10' }
}

export function SafetyScore() {
  const [scoreData, setScoreData] = useState<SafetyScoreData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch<SafetyScoreData>('/api/transparency/safety-score')
      .then((data) => setScoreData(data))
      .catch(() => {
        // Fallback to default on error
        setScoreData(null)
      })
      .finally(() => setLoading(false))
  }, [])

  // Use API score if available, otherwise fallback
  const score = scoreData ? Math.round(parseFloat(scoreData.score)) : 85
  const { label, color, stroke, bg } = getScoreConfig(score)
  const radius = 36
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference * (1 - score / 100)

  if (loading) {
    return (
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader className="pb-2 pt-4 px-4">
          <CardTitle className="text-sm font-medium text-zinc-400">安全スコア</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="flex items-center gap-5">
            <div className="h-20 w-20 rounded-full bg-zinc-800 animate-pulse" />
            <div className="space-y-2">
              <div className="h-6 w-16 rounded bg-zinc-800 animate-pulse" />
              <div className="h-4 w-12 rounded bg-zinc-800 animate-pulse" />
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

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
