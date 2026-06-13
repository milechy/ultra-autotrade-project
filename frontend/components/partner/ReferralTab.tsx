'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import Link from 'next/link'
import { Users } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export function ReferralTab() {
  const t = useTranslations('PartnerReferralTab')

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Users className="h-4 w-4" />
          {t('title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {t('description')}
        </p>
        <Button asChild variant="outline" size="sm">
          <Link href="/partner/referral">{t('manageLink')}</Link>
        </Button>
      </CardContent>
    </Card>
  )
}
