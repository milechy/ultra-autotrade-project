'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { RiskProfile } from './types'

interface RiskModeSelectorProps {
  profiles: RiskProfile[]
  current: string
  onSelect: (name: string) => void
  className?: string
}

export function RiskModeSelector({ profiles, current, onSelect, className }: RiskModeSelectorProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">リスクモード</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-3">
          {profiles.map((profile) => {
            const isSelected = profile.name === current
            return (
              <button
                key={profile.name}
                onClick={() => onSelect(profile.name)}
                className={cn(
                  'w-full rounded-lg border p-4 text-left transition-all duration-200',
                  isSelected
                    ? 'border-primary border-2 bg-primary/5'
                    : 'border-border hover:border-primary/50 hover:bg-muted/50'
                )}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <p className={cn('font-semibold', isSelected && 'text-primary')}>
                      {profile.name_ja}
                    </p>
                    <span className="text-sm text-muted-foreground">
                      最大借入 {profile.max_borrow_pct}%
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{profile.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {profile.allowed_assets.map((asset) => (
                      <span
                        key={asset}
                        className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold bg-secondary text-secondary-foreground"
                      >
                        {asset}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    最低健全度: {profile.min_health_factor}
                  </p>
                </div>
              </button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}