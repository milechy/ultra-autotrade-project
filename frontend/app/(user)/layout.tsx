// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import { WagmiRootProvider } from '@/lib/wallet/WagmiRootProvider'
import { UserProviders } from '@/components/user/UserProviders'
import { UserHeader } from '@/components/user/UserHeader'
import { BottomNav } from '@/components/shared/BottomNav'

export default async function UserAppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const locale = await getLocale()
  const messages = await getMessages()
  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <WagmiRootProvider>
        <UserProviders>
          <UserHeader />
          <div className="min-h-screen pb-16">
            {children}
          </div>
          <BottomNav />
        </UserProviders>
      </WagmiRootProvider>
    </NextIntlClientProvider>
  )
}
