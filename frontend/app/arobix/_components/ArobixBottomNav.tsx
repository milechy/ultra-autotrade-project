'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, CreditCard, Send, PieChart, User } from 'lucide-react'

const ITEMS = [
  { href: '/arobix/dashboard', label: 'Home', icon: Home },
  { href: '/arobix/dashboard#cards', label: 'Cards', icon: CreditCard },
  { href: '/arobix/send', label: 'Send', icon: Send },
  { href: '/arobix/dashboard#stats', label: 'Stats', icon: PieChart },
  { href: '/arobix/dashboard#me', label: 'Me', icon: User },
]

export function ArobixBottomNav() {
  const pathname = usePathname()
  return (
    <nav
      className="ax-shadow-card"
      style={{
        position: 'fixed',
        left: '50%',
        transform: 'translateX(-50%)',
        bottom: 14,
        width: 'min(380px, calc(100% - 32px))',
        background: 'var(--nav-bg)',
        borderRadius: 'var(--radius-pill)',
        padding: '10px 14px',
        zIndex: 50,
      }}
    >
      <div className="flex items-center justify-between">
        {ITEMS.map(({ href, label, icon: Icon }) => {
          const base = href.split('#')[0]
          const active = pathname === base
          return (
            <Link
              key={label}
              href={href}
              aria-label={label}
              className="flex flex-1 flex-col items-center gap-1 py-1"
              style={{ color: active ? 'var(--nav-active)' : 'var(--nav-fg)' }}
            >
              <Icon className="h-5 w-5" strokeWidth={active ? 2.4 : 1.9} />
              <span style={{ fontSize: 10, fontWeight: active ? 700 : 500 }}>{label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
