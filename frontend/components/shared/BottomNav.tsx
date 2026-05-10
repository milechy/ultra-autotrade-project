'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, CheckCircle, Brain, Settings, HelpCircle, Users, ClipboardList, Gift } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth'

const adminNavItems = [
  { href: '/user/dashboard', label: 'ホーム', icon: Home },
  { href: '/user/approve', label: '承認', icon: CheckCircle },
  { href: '/user/ai-feed', label: 'AI判定', icon: Brain },
  { href: '/user/settings', label: '設定', icon: Settings },
]

// partner (非 admin) が user レイアウト配下の画面 (/user/approve 等) に
// 居ても、パートナー画面に戻れるようにパートナー導線を提示する。
const partnerNavItems = [
  { href: '/partner/dashboard', label: 'ホーム', icon: Home },
  { href: '/user/approve', label: '承認', icon: CheckCircle },
  { href: '/partner/users', label: 'テスター', icon: Users },
  { href: '/partner/referral', label: '紹介', icon: Gift },
  { href: '/partner/proposals', label: 'AI提案', icon: ClipboardList },
  { href: '/partner/settings', label: '設定', icon: Settings },
]

const viewerNavItems = [
  { href: '/user/dashboard', label: 'ホーム', icon: Home },
  { href: '/user/ai-feed', label: 'AI判定', icon: Brain },
  { href: '/user/help', label: 'ヘルプ', icon: HelpCircle },
]

export function BottomNav() {
  const pathname = usePathname()
  const { isAdmin, isPartner } = useAuth()
  // partner (admin でも)はパートナー導線を優先。admin はパートナー扱いだが
  // admin 専用メニューを優先するため先に判定する。
  const navItems = isAdmin
    ? adminNavItems
    : isPartner
      ? partnerNavItems
      : viewerNavItems

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t bg-background md:hidden">
      <div className="flex items-center justify-around">
        {navItems.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex flex-1 flex-col items-center gap-1 py-3 text-xs transition-colors',
                isActive
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className={cn('h-5 w-5', isActive && 'text-primary')} />
              <span>{label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}