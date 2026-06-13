// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getLocale, getMessages } from 'next-intl/server'
import { NextIntlClientProvider } from 'next-intl'
import { AdminProviders } from '@/components/providers/AdminProviders'
import TermsGuard from '@/components/terms/TermsGuard'

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const locale = await getLocale()
  const messages = await getMessages()
  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <AdminProviders>
        <TermsGuard>{children}</TermsGuard>
      </AdminProviders>
    </NextIntlClientProvider>
  )
}
