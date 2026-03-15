'use client'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertTriangle, Wallet, Brain, CheckCircle } from 'lucide-react'
import Link from 'next/link'

const steps = [
  {
    number: 1,
    icon: Wallet,
    title: 'ウォレットを接続',
    description: 'MetaMask / WalletConnect 対応ウォレットをArbitrumネットワークに接続',
  },
  {
    number: 2,
    icon: Brain,
    title: 'AIが市場を分析',
    description: 'Claude Opus が最適なタイミングを提案。GPT-4o でクロス検証。',
  },
  {
    number: 3,
    icon: CheckCircle,
    title: 'あなたが承認・署名',
    description: '提案を確認し、ウォレットで署名。あなたが最終判断者です。',
  },
]

export default function LandingPage() {
  return (
    <main className="min-h-[calc(100vh-4rem)] px-4 py-8">
      <div className="max-w-md mx-auto space-y-8">
        {/* Hero */}
        <div className="text-center space-y-6 pt-8">
          <h1 className="text-2xl font-bold tracking-tight leading-snug">
            AIが最適なタイミングで、<br />あなたの資産を運用します
          </h1>
          <Button size="lg" className="w-full text-base font-semibold" asChild>
            <Link href="/user/wallet">
              <Wallet className="mr-2 h-5 w-5" />
              Connect Wallet
            </Link>
          </Button>
          <p className="text-xs text-muted-foreground">
            Non-custodial — あなたのウォレット、あなたの資産
          </p>
        </div>

        {/* Powered by */}
        <div className="flex flex-col items-center space-y-2">
          <span className="text-xs text-muted-foreground uppercase tracking-widest">
            Powered by
          </span>
          <div className="flex gap-2">
            <Badge variant="outline" className="text-blue-400 border-blue-400/50">
              Aave V3
            </Badge>
            <Badge variant="outline" className="text-cyan-400 border-cyan-400/50">
              Arbitrum One
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
            これは投資助言ではありません。暗号資産取引には元本損失のリスクがあります。ご自身の判断と責任において利用してください。
          </AlertDescription>
        </Alert>

        {/* Dashboard CTA */}
        <div className="text-center pb-4">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/user/dashboard" className="text-xs text-muted-foreground">
              すでに接続済みの方はダッシュボードへ →
            </Link>
          </Button>
        </div>
      </div>
    </main>
  )
}
