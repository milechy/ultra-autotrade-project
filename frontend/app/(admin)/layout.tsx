import { AdminProviders } from '@/components/providers/AdminProviders'

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <AdminProviders>{children}</AdminProviders>
}
