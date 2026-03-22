// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { WagmiRootProvider } from '@/lib/wallet/WagmiRootProvider'
import { UserProviders } from '@/components/user/UserProviders'
import { UserLayout } from '@/components/layout'

export default function UserAppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <WagmiRootProvider>
      <UserProviders>
        <UserLayout>{children}</UserLayout>
      </UserProviders>
    </WagmiRootProvider>
  )
}
