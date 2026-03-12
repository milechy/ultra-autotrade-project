'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, TrendingUp, Brain, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/user/dashboard', label: 'ホーム', icon: Home },
  { href: '/user/trade', label: '取引', icon: TrendingUp },
  { href: '/user/ai-feed', label: 'AI判定', icon: Brain },
  { href: '/user/settings', label: '設定', icon: Settings },
]

export function BottomNav() {
  const pathname = usePathname()

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
