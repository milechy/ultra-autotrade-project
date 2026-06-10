'use client'

import Link from 'next/link'
import { ArrowRight, Sparkles, ShieldCheck, Wallet } from 'lucide-react'

export default function ArobixOnboardingPage() {
  return (
    <div
      className="ax-gradient"
      style={{
        minHeight: '100dvh',
        display: 'flex',
        flexDirection: 'column',
        padding: '28px 24px 32px',
      }}
    >
      {/* ブランド */}
      <div className="flex items-center gap-2">
        <span
          className="ax-card-surface ax-r-pill flex items-center justify-center"
          style={{ width: 36, height: 36 }}
        >
          <Sparkles className="h-4 w-4 ax-accent-purple" />
        </span>
        <span className="ax-text-on-grad" style={{ fontWeight: 700, fontSize: 18, letterSpacing: '-0.02em' }}>
          Arobix
        </span>
      </div>

      {/* イラストエリア（右側に浮かぶカード群） */}
      <div style={{ flex: 1, position: 'relative', marginTop: 8 }}>
        <div
          className="ax-card-warm ax-r-card ax-shadow-card"
          style={{ position: 'absolute', right: 0, top: 36, width: 188, height: 116, transform: 'rotate(6deg)', padding: 16 }}
        >
          <p className="ax-text-secondary" style={{ fontSize: 11 }}>Total balance</p>
          <p className="ax-text-primary" style={{ fontSize: 22, fontWeight: 800 }}>$12,480.50</p>
          <div className="ax-card-pink ax-r-pill" style={{ display: 'inline-block', marginTop: 8, padding: '3px 10px' }}>
            <span className="ax-accent-pink" style={{ fontSize: 11, fontWeight: 700 }}>+2.4% today</span>
          </div>
        </div>
        <div
          className="ax-card-pink ax-r-card ax-shadow-soft"
          style={{ position: 'absolute', left: 4, top: 150, width: 150, height: 92, transform: 'rotate(-7deg)', padding: 14 }}
        >
          <Wallet className="h-5 w-5 ax-accent-pink" />
          <p className="ax-text-primary" style={{ fontSize: 13, fontWeight: 700, marginTop: 10 }}>Smart Wallet</p>
          <p className="ax-text-secondary" style={{ fontSize: 11 }}>•••• 4821</p>
        </div>
        <div
          className="ax-card-surface ax-r-card ax-shadow-soft"
          style={{ position: 'absolute', right: 26, top: 188, width: 132, padding: 12, display: 'flex', alignItems: 'center', gap: 10 }}
        >
          <span className="ax-card-warm-soft ax-r-pill flex items-center justify-center" style={{ width: 30, height: 30 }}>
            <ShieldCheck className="h-4 w-4 ax-accent-yellow" />
          </span>
          <span className="ax-text-primary" style={{ fontSize: 11, fontWeight: 600 }}>Insured & secure</span>
        </div>
      </div>

      {/* コピー（左寄せ） */}
      <div style={{ marginTop: 8 }}>
        <h1
          className="ax-text-on-grad"
          style={{ fontSize: 34, lineHeight: 1.12, fontWeight: 800, letterSpacing: '-0.03em', maxWidth: 300 }}
        >
          Money that feels effortless.
        </h1>
        <p className="ax-text-on-grad" style={{ marginTop: 12, fontSize: 15, opacity: 0.78, maxWidth: 280 }}>
          Save, send and grow your balance — all in one warm, simple place.
        </p>
      </div>

      {/* Get Started（ダークボタン） */}
      <Link
        href="/arobix/dashboard"
        className="ax-btn-primary"
        style={{
          marginTop: 24,
          height: 58,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 10,
          fontSize: 16,
          fontWeight: 700,
        }}
      >
        Get Started
        <ArrowRight className="h-5 w-5" />
      </Link>
      <p className="ax-text-on-grad" style={{ textAlign: 'center', marginTop: 14, fontSize: 13, opacity: 0.7 }}>
        Already have an account? <span style={{ fontWeight: 700 }}>Sign in</span>
      </p>
    </div>
  )
}
