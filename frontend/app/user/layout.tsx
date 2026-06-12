// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import { WagmiRootProvider } from '@/lib/wallet/WagmiRootProvider'
import { UserProviders } from '@/components/user/UserProviders'
import { BrowserTermsGate } from '@/components/user/BrowserTermsGate'
import { UserHeader } from '@/components/user/UserHeader'
import { BottomNav } from '@/components/shared/BottomNav'
import { UserErrorBoundary } from './_components/UserErrorBoundary'
import { EmergencyStopFloat } from '@/components/shared/EmergencyStopFloat'

export default async function UserLayout({
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
          <BrowserTermsGate>
            <UserErrorBoundary>
              <UserHeader />
              <div className="min-h-screen pb-16">
                {children}
              </div>
              <BottomNav />
              <EmergencyStopFloat />
            </UserErrorBoundary>
          </BrowserTermsGate>
        </UserProviders>
      </WagmiRootProvider>
    </NextIntlClientProvider>
  )
}
