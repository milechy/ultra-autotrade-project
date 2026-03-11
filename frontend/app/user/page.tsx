import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { TrendingUp, Shield, Brain } from 'lucide-react'

export default function LandingPage() {
  return (
    <main className="min-h-[calc(100vh-4rem)] px-4 py-8">
      <div className="max-w-md mx-auto space-y-8">
        {/* Hero */}
        <div className="text-center space-y-3 pt-8">
          <h1 className="text-3xl font-bold tracking-tight">Ultra AutoTrade</h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            AI駆動の自動取引プラットフォーム。<br />
            Aave × Bybit でスマートに資産を運用。
          </p>
        </div>

        {/* Feature cards */}
        <div className="space-y-3">
          <FeatureCard
            icon={<Brain className="h-5 w-5 text-primary" />}
            title="AI判定エンジン"
            description="Claude Opus が市場を分析し、BUY / SELL / HOLD を自動判定。GPT-4o でクロス検証。"
          />
          <FeatureCard
            icon={<Shield className="h-5 w-5 text-primary" />}
            title="安全設計"
            description="Health Factor 1.6未満で自動停止。資産を守るルールエンジン搭載。"
          />
          <FeatureCard
            icon={<TrendingUp className="h-5 w-5 text-primary" />}
            title="Aave × Bybit"
            description="Arbitrum上のAaveポジションを活用しながらBybitで取引。"
          />
        </div>

        {/* CTA */}
        <div className="flex flex-col gap-3 pt-4">
          <Button asChild size="lg" className="w-full">
            <Link href="/user/wallet">ウォレットを接続して始める</Link>
          </Button>
          <Button asChild variant="outline" size="lg" className="w-full">
            <Link href="/user/dashboard">ダッシュボードを見る</Link>
          </Button>
        </div>
      </div>
    </main>
  )
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 pt-4 pb-4">
        <div className="mt-0.5 shrink-0">{icon}</div>
        <div>
          <p className="font-medium text-sm">{title}</p>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{description}</p>
        </div>
      </CardContent>
    </Card>
  )
}
