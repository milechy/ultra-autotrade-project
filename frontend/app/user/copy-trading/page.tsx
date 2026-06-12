'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

export const dynamic = 'force-dynamic'

import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, RefreshCw } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/lib/auth'
import { UserProviders } from '@/components/user/UserProviders'
import AuthGuard from '@/components/AuthGuard'
import { CopyTradingCard } from '@/components/user/CopyTradingCard'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  getStrategies,
  getSubscriptions,
  subscribeStrategy,
  unsubscribeStrategy,
  type StrategyWithPerformance,
  type CopySubscription,
} from '@/lib/api/copy_trading'

function CopyTradingPage() {
  const { token } = useAuth()
  const t = useTranslations('CopyTrading')
  const tCommon = useTranslations('Common')

  const [strategies, setStrategies] = useState<StrategyWithPerformance[]>([])
  const [subscriptions, setSubscriptions] = useState<CopySubscription[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      const [strats, subs] = await Promise.all([
        getStrategies(token),
        getSubscriptions(token),
      ])
      setStrategies(strats)
      setSubscriptions(subs)
    } catch {
      setError(tCommon('error'))
    } finally {
      setIsLoading(false)
    }
  }, [token, tCommon])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const subscribedStrategyIds = new Set(subscriptions.map(s => s.strategy_id))

  const handleSubscribe = async (strategy: StrategyWithPerformance) => {
    if (!token) return
    try {
      const sub = await subscribeStrategy(
        strategy.id,
        { follower_id: 'me', copy_ratio: 0.5 },
        token
      )
      setSubscriptions(prev => [...prev, sub])
      setSuccessMsg(t('subscribeSuccess'))
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch {
      setError(tCommon('error'))
    }
  }

  const handleUnsubscribe = async (strategyId: string) => {
    if (!token) return
    try {
      await unsubscribeStrategy(strategyId, token)
      setSubscriptions(prev => prev.filter(s => s.strategy_id !== strategyId))
      setSuccessMsg(t('unsubscribeSuccess'))
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch {
      setError(tCommon('error'))
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen text-muted-foreground">
        <RefreshCw className="mb-3 h-8 w-8 animate-spin" />
        <p className="text-sm">{tCommon('loading')}</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="flex items-center gap-2 px-4 py-3">
          <TrendingUp className="h-5 w-5" />
          <h1 className="text-lg font-semibold">{t('title')}</h1>
        </div>
        <p className="px-4 pb-3 text-xs text-muted-foreground">{t('subtitle')}</p>
      </div>

      <div className="space-y-4 px-4 py-4 pb-8">
        <div className="relative">
          <div className="absolute inset-0 bg-white dark:bg-gray-900/80 backdrop-blur-sm z-10 flex flex-col items-center justify-center rounded-lg">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-700 mb-2">Coming Soon</p>
              <p className="text-gray-500">{t('comingSoon')}</p>
            </div>
          </div>
          <div className="pointer-events-none select-none">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {successMsg && (
              <Alert>
                <AlertDescription>{successMsg}</AlertDescription>
              </Alert>
            )}

            <section>
              <h2 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                {t('strategies')}
              </h2>
              {strategies.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('noStrategies')}</p>
              ) : (
                <div className="space-y-3">
                  {strategies.map(strategy => (
                    <CopyTradingCard
                      key={strategy.id}
                      strategy={strategy}
                      isSubscribed={subscribedStrategyIds.has(strategy.id)}
                      onSubscribe={handleSubscribe}
                      onUnsubscribe={handleUnsubscribe}
                    />
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function CopyTradingPageWrapper() {
  return (
    <UserProviders>
      <AuthGuard>
        <CopyTradingPage />
      </AuthGuard>
    </UserProviders>
  )
}
