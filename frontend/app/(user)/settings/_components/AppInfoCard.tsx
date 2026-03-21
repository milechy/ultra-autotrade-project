// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { ExternalLink } from 'lucide-react'

const APP_VERSION = 'v0.1.0-staging'
const SUPPORT_EMAIL = 'support@ultra-autotrade.com'

export function AppInfoCard() {
  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-zinc-100">アプリ情報</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* バージョン */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-400">バージョン</span>
          <span className="text-sm font-mono text-zinc-300">{APP_VERSION}</span>
        </div>

        <Separator className="bg-zinc-800" />

        {/* リンク */}
        <div className="space-y-2">
          <p className="text-xs text-zinc-500 font-medium uppercase tracking-wide">法的情報</p>
          <div className="space-y-1.5">
            <Link
              href="/terms"
              className="flex items-center justify-between text-sm text-zinc-300 hover:text-zinc-100 transition-colors py-1"
            >
              <span>利用規約</span>
              <ExternalLink className="h-3.5 w-3.5 text-zinc-500" />
            </Link>
            <Link
              href="/privacy"
              className="flex items-center justify-between text-sm text-zinc-300 hover:text-zinc-100 transition-colors py-1"
            >
              <span>プライバシーポリシー</span>
              <ExternalLink className="h-3.5 w-3.5 text-zinc-500" />
            </Link>
            <Link
              href="/risk-disclosure"
              className="flex items-center justify-between text-sm text-zinc-300 hover:text-zinc-100 transition-colors py-1"
            >
              <span>リスク開示</span>
              <ExternalLink className="h-3.5 w-3.5 text-zinc-500" />
            </Link>
          </div>
        </div>

        <Separator className="bg-zinc-800" />

        {/* サポート */}
        <div className="space-y-1">
          <p className="text-xs text-zinc-500 font-medium uppercase tracking-wide">サポート</p>
          <a
            href={`mailto:${SUPPORT_EMAIL}`}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            {SUPPORT_EMAIL}
          </a>
        </div>
      </CardContent>
    </Card>
  )
}
