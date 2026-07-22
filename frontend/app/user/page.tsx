'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertTriangle, Wallet, Brain, CheckCircle } from 'lucide-react'
import Link from 'next/link'

const STEP_ICONS = [Wallet, Brain, CheckCircle] as const

export default function LandingPage() {
  const t = useTranslations('UserHome')

  const steps = [
    { number: 1, icon: STEP_ICONS[0], title: t('step1.title'), description: t('step1.description') },
    { number: 2, icon: STEP_ICONS[1], title: t('step2.title'), description: t('step2.description') },
    { number: 3, icon: STEP_ICONS[2], title: t('step3.title'), description: t('step3.description') },
  ]

  return (
    <main className="min-h-[calc(100vh-4rem)] px-4 py-8">
      <div className="max-w-md mx-auto space-y-8">
        {/* Hero */}
        <div className="text-center space-y-6 pt-8">
          <h1 className="text-2xl font-bold tracking-tight leading-snug">
            {t('heroLine1')}<br />{t('heroLine2')}
          </h1>
          <Button size="lg" className="w-full text-base font-semibold" asChild>
            <Link href="/user/wallet">
              <Wallet className="mr-2 h-5 w-5" />
              Connect Wallet
            </Link>
          </Button>
          <p className="text-xs text-muted-foreground">
            {t('nonCustodial')}
          </p>
        </div>

        {/* Powered by */}
        <div className="flex flex-col items-center space-y-2">
          <span className="text-xs text-muted-foreground uppercase tracking-widest">
            Powered by
          </span>
          {/* 消費者向け UI に DeFi プロトコル名（Aave 等）は出さない約束のため、
              「Powered by」バッジからプロトコル名を除去。チェーン名(Base)は残す。 */}
          <div className="flex gap-2">
            <Badge variant="outline" className="text-indigo-400 border-indigo-400/50">
              Base Mainnet
            </Badge>
          </div>
        </div>

        {/* 3-step explanation */}
        <div className="space-y-3">
          {steps.map(({ number, icon: Icon, title, description }) => (
            <Card key={number} className="border-border/50 bg-card/50">
              <CardContent className="flex items-start gap-4 p-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm">
                  {number}
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <p className="text-sm font-semibold">{title}</p>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {description}
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Risk disclaimer */}
        <Alert className="border-amber-500/50 bg-amber-500/10 text-amber-400">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
          <AlertDescription className="text-xs leading-relaxed text-amber-400/90">
            {t('riskDisclaimer')}
          </AlertDescription>
        </Alert>

        {/* Dashboard CTA */}
        <div className="text-center pb-4">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/user/dashboard" className="text-xs text-muted-foreground">
              {t('dashboardCta')}
            </Link>
          </Button>
        </div>
      </div>
    </main>
  )
}
