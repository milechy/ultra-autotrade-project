import { UserProviders } from '@/components/user/UserProviders'
import { UserHeader } from '@/components/user/UserHeader'
import { BottomNav } from '@/components/shared/BottomNav'
import { EmergencyStopButton } from '@/components/emergency/EmergencyStopButton'

export default function UserLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <UserProviders>
      <UserHeader />
      <div className="min-h-screen pb-16">
        {children}
      </div>
      <BottomNav />
      <EmergencyStopButton />
    </UserProviders>
  )
}
