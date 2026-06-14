// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { AlertTriangle, Home } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getTranslations } from 'next-intl/server'

export default async function NotFound() {
  const t = await getTranslations('NotFound')

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center px-4">
      <div className="max-w-md w-full text-center space-y-8">
        {/* Icon */}
        <div className="flex justify-center">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-blue-500/10 border border-blue-500/20">
            <AlertTriangle className="h-10 w-10 text-blue-400" />
          </div>
        </div>

        {/* Error Code */}
        <div>
          <p className="text-6xl font-bold text-blue-500 mb-2">404</p>
          <h1 className="text-2xl font-bold text-white mb-3">
            {t('title')}
          </h1>
          <p className="text-gray-400 text-sm leading-relaxed">
            {t('description')}
          </p>
        </div>

        {/* Divider */}
        <div className="border-t border-gray-800" />

        {/* Branding */}
        <div>
          <p className="text-xs text-gray-600 uppercase tracking-widest mb-1">
            Ultra AutoTrade
          </p>
          <p className="text-xs text-gray-600">
            {t('suggestion')}
          </p>
        </div>

        {/* Home Button */}
        <Button
          asChild
          size="lg"
          className="bg-blue-500 hover:bg-blue-600 text-white px-8 py-5 h-auto w-full sm:w-auto"
        >
          <Link href="/">
            <Home className="mr-2 h-4 w-4" />
            {t('homeButton')}
          </Link>
        </Button>
      </div>
    </div>
  )
}
