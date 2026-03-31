// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
export const dynamic = 'force-dynamic'

import { NextIntlClientProvider } from 'next-intl'
import { getMessages } from 'next-intl/server'

export default async function CopyTradingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const messages = await getMessages()
  return (
    <NextIntlClientProvider messages={messages}>
      {children}
    </NextIntlClientProvider>
  )
}
