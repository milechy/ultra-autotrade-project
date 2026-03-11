import { UserProviders } from '@/components/user/UserProviders'
import { BottomNav } from '@/components/shared/BottomNav'

export default function UserLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <UserProviders>
      <div className="min-h-screen pb-16">
        {children}
        <BottomNav />
      </div>
    </UserProviders>
  )
}
