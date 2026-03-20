// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { AdminProviders } from '@/components/providers/AdminProviders'
import TermsGuard from '@/components/terms/TermsGuard'

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AdminProviders>
      <TermsGuard>{children}</TermsGuard>
    </AdminProviders>
  )
}
