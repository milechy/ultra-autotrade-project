'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Sparkles, Brain, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { apiPut } from '@/lib/api/client'
import { useAuth } from '@/lib/auth'

type UserMode = 'managed' | 'active'

interface ModeCardProps {
  mode: UserMode
  icon: React.ReactNode
  title: string
  badge?: string
  bullets: string[]
  isLoading: boolean
  onSelect: (mode: UserMode) => void
}

function ModeCard({ mode, icon, title, badge, bullets, isLoading, onSelect }: ModeCardProps) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 space-y-4 flex flex-col">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-800 text-zinc-100">
            {icon}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-zinc-100">{title}</h2>
              {badge && (
                <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-400">
                  {badge}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <ul className="space-y-2 flex-1">
        {bullets.map((bullet) => (
          <li key={bullet} className="flex items-start gap-2 text-sm text-zinc-300">
            <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-500" />
            <span>{bullet}</span>
          </li>
        ))}
      </ul>

      <button
        onClick={() => onSelect(mode)}
        disabled={isLoading}
        className="mt-2 w-full rounded-xl bg-zinc-100 py-3 text-sm font-semibold text-zinc-900 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>保存中...</span>
          </>
        ) : (
          'このモードで始める'
        )}
      </button>
    </div>
  )
}

export default function OnboardingPage() {
  const router = useRouter()
  const { isAdmin, isLoading: authLoading } = useAuth()
  const [loadingMode, setLoadingMode] = useState<UserMode | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Non-admin users don't need onboarding; redirect to dashboard
  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.replace('/user/dashboard')
    }
  }, [authLoading, isAdmin, router])

  if (!isAdmin) return null

  const handleSelect = async (mode: UserMode) => {
    setLoadingMode(mode)
    setError(null)
    try {
      await apiPut('/api/user/settings', { user_mode: mode })
      router.push('/user/dashboard')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'モードの設定に失敗しました。もう一度お試しください。')
      setLoadingMode(null)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 px-4 py-10">
      <div className="mx-auto max-w-md space-y-8">
        {/* Header */}
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-bold text-zinc-100">運用モードを選択</h1>
          <p className="text-sm text-zinc-400">あなたに合った運用スタイルを選んでください</p>
        </div>

        {/* Error message */}
        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-red-800 bg-red-950/50 px-4 py-3 text-sm text-red-400">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Mode cards */}
        <div className="space-y-4">
          <ModeCard
            mode="managed"
            icon={<Sparkles className="h-6 w-6" />}
            title="完全おまかせモード"
            badge="おすすめ"
            bullets={[
              '入金したらAIが全自動で運用します',
              '危険時は自動で資産を守ります',
              '結果はLINEでお知らせ',
            ]}
            isLoading={loadingMode === 'managed'}
            onSelect={handleSelect}
          />

          <ModeCard
            mode="active"
            icon={<Brain className="h-6 w-6" />}
            title="アクティブモード"
            bullets={[
              'AIの提案を確認して自分で承認',
              'リスク設定を3段階から選択可能',
              '判定の詳細を全て確認できます',
            ]}
            isLoading={loadingMode === 'active'}
            onSelect={handleSelect}
          />
        </div>
      </div>
    </div>
  )
}
