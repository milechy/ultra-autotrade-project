'use client'

import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ImpactData, PortfolioState } from './types'

interface ImpactCardProps {
  data: ImpactData
  className?: string
}

function formatJpy(amount: number): string {
  return (amount ?? 0).toLocaleString('ja-JP')
}

function PortfolioColumn({
  state,
  label,
  highlighted,
}: {
  state: PortfolioState
  label: string
  highlighted?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-lg border p-4 flex flex-col gap-2',
        highlighted ? 'border-primary border-2 bg-primary/5' : 'border-border'
      )}
    >
      <p className={cn('text-sm font-semibold', highlighted && 'text-primary')}>{label}</p>
      <div className="flex flex-col gap-1 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">預け入れ</span>
          <span>${(state.deposit_usd ?? 0).toLocaleString()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">借入</span>
          <span>${(state.borrow_usd ?? 0).toLocaleString()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">年利</span>
          <span>{(state.net_apy ?? 0).toFixed(2)}%</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">年間収益</span>
          <span>¥{formatJpy(state.yield_annual_jpy)}</span>
        </div>
        {state.health_factor !== null && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">健全度</span>
            <span>{(state.health_factor ?? 0).toFixed(2)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function ImpactCard({ data, className }: ImpactCardProps) {
  if (!data) return null
  const diffPositive = data.diff_yield_annual_jpy >= 0

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          {data.action_type} ${(data.amount_usd ?? 0).toLocaleString()} の影響
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <PortfolioColumn state={data.before} label="実行しない場合" />
          <PortfolioColumn state={data.after} label="実行した場合" highlighted />
        </div>

        {/* Diff summary */}
        <div className="rounded-lg bg-muted p-3 flex flex-col gap-1">
          <p className={cn('text-lg font-bold', diffPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
            {diffPositive ? '+' : ''}¥{formatJpy(data.diff_yield_annual_jpy)} / 年
          </p>
          <p className="text-sm text-muted-foreground">{data.metaphor}</p>
        </div>
      </CardContent>
    </Card>
  )
}
