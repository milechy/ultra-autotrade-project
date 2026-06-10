'use client'

import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

const SCREENS = [
  { href: '/arobix/onboarding', title: 'Onboarding', desc: 'Welcome / Get Started' },
  { href: '/arobix/dashboard', title: 'Dashboard', desc: 'Balance · Quick actions · Cards' },
  { href: '/arobix/send', title: 'Send Money', desc: 'Tabs · Cards · Contacts' },
]

export default function ArobixIndexPage() {
  return (
    <div style={{ padding: '32px 22px' }}>
      <p className="ax-accent-purple" style={{ fontSize: 13, fontWeight: 700 }}>UAT × Arobix</p>
      <h1 className="ax-text-primary" style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.03em', marginTop: 4 }}>
        Theme preview
      </h1>
      <p className="ax-text-secondary" style={{ marginTop: 8, fontSize: 14 }}>
        柔らかく上品なプレミアムフィンテックテイスト。3 画面をご確認ください。
      </p>

      <div style={{ marginTop: 26, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {SCREENS.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            className="ax-card-warm ax-r-card ax-shadow-soft flex items-center justify-between"
            style={{ padding: 20 }}
          >
            <div>
              <p className="ax-text-primary" style={{ fontSize: 17, fontWeight: 800 }}>{s.title}</p>
              <p className="ax-text-secondary" style={{ fontSize: 13, marginTop: 2 }}>{s.desc}</p>
            </div>
            <span
              className="ax-btn-primary flex items-center justify-center"
              style={{ width: 42, height: 42, borderRadius: 14 }}
            >
              <ArrowRight className="h-5 w-5" />
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
