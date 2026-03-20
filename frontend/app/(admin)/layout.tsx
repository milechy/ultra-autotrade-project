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
