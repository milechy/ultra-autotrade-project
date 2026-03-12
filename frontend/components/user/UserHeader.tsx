'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/user/dashboard', label: 'ダッシュボード' },
  { href: '/user/ai-feed', label: 'AI判定' },
  { href: '/user/trade', label: '取引承認' },
  { href: '/user/history', label: '取引履歴' },
  { href: '/user/settings', label: '設定' },
  { href: '/user/grid', label: 'Grid Bot' },
  { href: '/user/copy-trading', label: 'Copy Trading' },
  { href: '/user/wallet', label: 'ウォレット' },
]

export function UserHeader() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()

  const handleLogout = async () => {
    await logout()
    router.push('/login')
  }

  return (
    <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
      <div className="flex items-center justify-between px-4 py-2">
        <Link href="/user/dashboard" className="font-bold text-sm shrink-0">
          Ultra AutoTrade
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1 overflow-x-auto">
          {navItems.map(({ href, label }) => {
            const isActive = pathname === href || pathname.startsWith(href + '/')
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  'px-3 py-1.5 rounded text-xs whitespace-nowrap transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                )}
              >
                {label}
              </Link>
            )
          })}
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          {user && (
            <span className="hidden md:block text-xs text-muted-foreground">
              {user.username}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="text-xs border rounded px-2 py-1 text-muted-foreground hover:text-foreground transition-colors"
          >
            ログアウト
          </button>
        </div>
      </div>

      {/* Mobile nav scroll */}
      <div className="md:hidden flex overflow-x-auto border-t scrollbar-none">
        {navItems.map(({ href, label }) => {
          const isActive = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'px-3 py-2 text-xs whitespace-nowrap shrink-0 border-b-2 transition-colors',
                isActive
                  ? 'border-primary text-primary font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              {label}
            </Link>
          )
        })}
      </div>
    </header>
  )
}
