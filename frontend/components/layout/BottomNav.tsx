'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Brain, CheckCircle, History, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/dashboard', label: 'ダッシュボード', icon: LayoutDashboard },
  { href: '/decisions', label: 'AI', icon: Brain },
  { href: '/approve', label: '承認', icon: CheckCircle },
  { href: '/history', label: '履歴', icon: History },
  { href: '/settings', label: '設定', icon: Settings },
]

interface BottomNavProps {
  pendingCount?: number
}

export function BottomNav({ pendingCount }: BottomNavProps) {
  const pathname = usePathname()

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-zinc-800 bg-zinc-900/95 backdrop-blur-sm md:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex h-16 items-center justify-around">
        {navItems.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + '/')
          const showBadge = href === '/approve' && pendingCount && pendingCount > 0

          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'relative flex flex-1 flex-col items-center gap-0.5 py-2 text-xs transition-colors',
                isActive ? 'text-blue-400' : 'text-zinc-500 hover:text-zinc-300',
              )}
            >
              <div className="relative">
                <Icon className={cn('h-5 w-5', isActive && 'fill-blue-400/20')} />
                {showBadge && (
                  <span className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                    {pendingCount > 9 ? '9+' : pendingCount}
                  </span>
                )}
              </div>
              <span>{label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
