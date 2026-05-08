'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import Link from 'next/link'
import { Users } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export function ReferralTab() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Users className="h-4 w-4" />
          紹介プログラム
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          招待リンクを発行して新しいユーザーを紹介できます。紹介したユーザーの取引履歴（種別/金額/日時）を確認できます。
        </p>
        <Button asChild variant="outline" size="sm">
          <Link href="/partner/referral">招待リンクを管理</Link>
        </Button>
      </CardContent>
    </Card>
  )
}
