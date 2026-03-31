'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useAuth } from '@/lib/auth'
import { EmergencyStopButton } from '@/components/shared'
import { UserHeader } from './UserHeader'
import { BottomNav } from './BottomNav'
import { toast } from 'sonner'
import { postJson } from '@/lib/api/http'

interface UserLayoutProps {
  children: React.ReactNode
  pendingCount?: number
}

export function UserLayout({ children, pendingCount }: UserLayoutProps) {
  const { token } = useAuth()

  const handleEmergencyStop = async () => {
    if (!token) return
    try {
      await postJson('/automation/emergency-stop', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      toast.success('緊急停止を実行しました')
    } catch {
      toast.error('緊急停止の実行に失敗しました')
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <UserHeader />

      {/* Main content: scrollable area between header and bottom nav */}
      <main
        className="overflow-y-auto"
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 4rem)' }}
      >
        {children}
      </main>

      <BottomNav pendingCount={pendingCount} />

      {/* Floating emergency stop: positioned above bottom nav */}
      <div className="fixed bottom-20 right-4 z-50">
        <EmergencyStopButton variant="inline" onStop={handleEmergencyStop} />
      </div>
    </div>
  )
}
