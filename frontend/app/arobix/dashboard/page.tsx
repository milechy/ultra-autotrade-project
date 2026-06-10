'use client'

import Link from 'next/link'
import {
  Plus,
  ArrowLeftRight,
  ReceiptText,
  Grid2x2,
  Bell,
  TrendingUp,
  ArrowUpRight,
  ArrowDownLeft,
  ShoppingBag,
} from 'lucide-react'
import { ArobixBottomNav } from '../_components/ArobixBottomNav'

const QUICK_ACTIONS = [
  { label: 'Top Up', icon: Plus },
  { label: 'Transfer', icon: ArrowLeftRight, href: '/arobix/send' },
  { label: 'Bills', icon: ReceiptText },
  { label: 'Others', icon: Grid2x2 },
]

const TRANSACTIONS = [
  { name: 'Apple Store', sub: 'Shopping · Today', amount: '-$129.00', icon: ShoppingBag, up: false },
  { name: 'Salary', sub: 'Income · Yesterday', amount: '+$3,200.00', icon: ArrowDownLeft, up: true },
  { name: 'Emma Wilson', sub: 'Transfer · Mon', amount: '-$48.50', icon: ArrowUpRight, up: false },
]

export default function ArobixDashboardPage() {
  return (
    <div style={{ paddingBottom: 110 }}>
      {/* グラデーションヘッダー */}
      <header
        className="ax-gradient-header"
        style={{
          padding: '24px 22px 64px',
          borderBottomLeftRadius: 34,
          borderBottomRightRadius: 34,
        }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span
              className="ax-card-surface ax-r-pill flex items-center justify-center"
              style={{ width: 42, height: 42, fontWeight: 700 }}
            >
              <span className="ax-accent-purple">A</span>
            </span>
            <div>
              <p className="ax-text-on-grad" style={{ fontSize: 12, opacity: 0.75 }}>Good morning</p>
              <p className="ax-text-on-grad" style={{ fontSize: 15, fontWeight: 700 }}>Alex Morgan</p>
            </div>
          </div>
          <span
            className="ax-card-surface ax-r-pill flex items-center justify-center"
            style={{ width: 40, height: 40 }}
          >
            <Bell className="h-5 w-5 ax-text-primary" />
          </span>
        </div>

        {/* 残高 */}
        <div style={{ marginTop: 26 }}>
          <p className="ax-text-on-grad" style={{ fontSize: 13, opacity: 0.78 }}>Total balance</p>
          <div className="flex items-end gap-3" style={{ marginTop: 4 }}>
            <h1 className="ax-text-on-grad" style={{ fontSize: 40, fontWeight: 800, letterSpacing: '-0.03em' }}>
              $12,480.50
            </h1>
            <span
              className="ax-card-surface ax-r-pill flex items-center gap-1"
              style={{ padding: '4px 9px', marginBottom: 8 }}
            >
              <TrendingUp className="h-3.5 w-3.5 ax-accent-purple" />
              <span className="ax-accent-purple" style={{ fontSize: 12, fontWeight: 700 }}>+2.4% 24h</span>
            </span>
          </div>
        </div>
      </header>

      {/* クイックアクション（ヘッダーに重ねる） */}
      <section style={{ padding: '0 18px', marginTop: -36 }}>
        <div className="ax-card-surface ax-r-card ax-shadow-card" style={{ padding: '18px 12px' }}>
          <div className="flex items-center justify-between">
            {QUICK_ACTIONS.map(({ label, icon: Icon, href }) => {
              const inner = (
                <div className="flex flex-col items-center gap-2" style={{ flex: 1 }}>
                  <span
                    className="ax-card-warm ax-r-btn flex items-center justify-center"
                    style={{ width: 50, height: 50 }}
                  >
                    <Icon className="h-5 w-5 ax-text-primary" />
                  </span>
                  <span className="ax-text-primary" style={{ fontSize: 12, fontWeight: 600 }}>{label}</span>
                </div>
              )
              return href ? (
                <Link key={label} href={href} style={{ flex: 1 }}>{inner}</Link>
              ) : (
                <div key={label} style={{ flex: 1 }}>{inner}</div>
              )
            })}
          </div>
        </div>
      </section>

      {/* My Cards */}
      <section id="cards" style={{ padding: '26px 18px 0' }}>
        <SectionHeader title="My Cards" action="See all" />
        <div className="flex gap-14" style={{ gap: 14, overflowX: 'auto', paddingBottom: 4 }}>
          <WarmCard
            tone="warm"
            brand="Premium"
            number="4821"
            balance="$8,240.00"
            name="ALEX MORGAN"
          />
          <WarmCard
            tone="pink"
            brand="Savings"
            number="0934"
            balance="$4,240.50"
            name="ALEX MORGAN"
          />
        </div>
      </section>

      {/* Recent Transactions */}
      <section id="stats" style={{ padding: '26px 18px 0' }}>
        <SectionHeader title="Recent Transaction" action="See all" />
        <div className="ax-card-surface ax-r-card ax-shadow-soft" style={{ padding: 8 }}>
          {TRANSACTIONS.map((tx, i) => (
            <div
              key={tx.name}
              className="flex items-center gap-3"
              style={{
                padding: '12px 10px',
                borderTop: i === 0 ? 'none' : '1px solid rgba(27,26,35,0.06)',
              }}
            >
              <span
                className={tx.up ? 'ax-card-warm-soft' : 'ax-card-pink'}
                style={{ width: 44, height: 44, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <tx.icon className={tx.up ? 'h-5 w-5 ax-accent-yellow' : 'h-5 w-5 ax-accent-pink'} />
              </span>
              <div style={{ flex: 1 }}>
                <p className="ax-text-primary" style={{ fontSize: 14, fontWeight: 700 }}>{tx.name}</p>
                <p className="ax-text-secondary" style={{ fontSize: 12 }}>{tx.sub}</p>
              </div>
              <span
                className="ax-text-primary"
                style={{ fontSize: 14, fontWeight: 700, color: tx.up ? 'var(--accent-purple)' : 'var(--text-primary)' }}
              >
                {tx.amount}
              </span>
            </div>
          ))}
        </div>
      </section>

      <ArobixBottomNav />
    </div>
  )
}

function SectionHeader({ title, action }: { title: string; action: string }) {
  return (
    <div className="flex items-center justify-between" style={{ marginBottom: 14 }}>
      <h2 className="ax-text-primary" style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em' }}>{title}</h2>
      <span className="ax-text-secondary" style={{ fontSize: 13, fontWeight: 600 }}>{action}</span>
    </div>
  )
}

function WarmCard({
  tone,
  brand,
  number,
  balance,
  name,
}: {
  tone: 'warm' | 'pink'
  brand: string
  number: string
  balance: string
  name: string
}) {
  return (
    <div
      className={`${tone === 'warm' ? 'ax-card-warm' : 'ax-card-pink'} ax-r-card ax-shadow-card`}
      style={{ minWidth: 248, padding: 20 }}
    >
      <div className="flex items-center justify-between">
        <span className="ax-text-primary" style={{ fontSize: 14, fontWeight: 700 }}>{brand}</span>
        <span
          className="ax-r-pill"
          style={{
            width: 30,
            height: 20,
            background: tone === 'warm' ? 'var(--accent-yellow)' : 'var(--accent-pink)',
            opacity: 0.85,
          }}
        />
      </div>
      <p className="ax-text-secondary" style={{ marginTop: 22, fontSize: 13, letterSpacing: '0.18em' }}>
        ••••  ••••  ••••  {number}
      </p>
      <div className="flex items-end justify-between" style={{ marginTop: 14 }}>
        <div>
          <p className="ax-text-secondary" style={{ fontSize: 11 }}>{name}</p>
          <p className="ax-text-primary" style={{ fontSize: 20, fontWeight: 800 }}>{balance}</p>
        </div>
        <span className="ax-text-secondary" style={{ fontSize: 12, fontWeight: 700, fontStyle: 'italic' }}>VISA</span>
      </div>
    </div>
  )
}
