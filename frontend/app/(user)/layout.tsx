// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import { PrivyRootProvider } from '@/lib/wallet/PrivyRootProvider'
import { UserProviders } from '@/components/user/UserProviders'
import { UserHeader } from '@/components/user/UserHeader'
import { BottomNav } from '@/components/shared/BottomNav'
import { EmergencyStopFloat } from '@/components/shared/EmergencyStopFloat'

export default async function UserAppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const locale = await getLocale()
  const messages = await getMessages()
  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <PrivyRootProvider>
        <UserProviders>
          <UserHeader />
          <div className="min-h-screen pb-16">
            {children}
          </div>
          <BottomNav />
          <EmergencyStopFloat />
        </UserProviders>
      </PrivyRootProvider>
    </NextIntlClientProvider>
  )
}
