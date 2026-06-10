'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ChevronLeft, Search, Plus } from 'lucide-react'
import { ArobixBottomNav } from '../_components/ArobixBottomNav'

const TABS = ['Cards', 'Accounts', 'Statement'] as const

const CONTACTS = [
  { name: 'Emma Wilson', handle: '@emma', tone: 'warm', initial: 'E' },
  { name: 'James Carter', handle: '@jcarter', tone: 'pink', initial: 'J' },
  { name: 'Sophia Lee', handle: '@sophia', tone: 'warm', initial: 'S' },
  { name: 'Noah Davis', handle: '@noahd', tone: 'pink', initial: 'N' },
  { name: 'Olivia Brown', handle: '@olivia', tone: 'warm', initial: 'O' },
]

export default function ArobixSendPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Cards')

  return (
    <div style={{ paddingBottom: 110 }}>
      {/* グラデーションヘッダー + タブ */}
      <header
        className="ax-gradient-header"
        style={{ padding: '22px 20px 26px', borderBottomLeftRadius: 30, borderBottomRightRadius: 30 }}
      >
        <div className="flex items-center justify-between">
          <Link
            href="/arobix/dashboard"
            className="ax-card-surface ax-r-pill flex items-center justify-center"
            style={{ width: 40, height: 40 }}
          >
            <ChevronLeft className="h-5 w-5 ax-text-primary" />
          </Link>
          <span className="ax-text-on-grad" style={{ fontSize: 17, fontWeight: 700 }}>Send Money</span>
          <span style={{ width: 40 }} />
        </div>

        {/* タブ */}
        <div
          className="ax-r-pill flex"
          style={{ marginTop: 20, padding: 4, background: 'rgba(255,255,255,0.32)' }}
        >
          {TABS.map((t) => {
            const active = t === tab
            return (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="ax-r-pill"
                style={{
                  flex: 1,
                  padding: '9px 0',
                  fontSize: 13,
                  fontWeight: 700,
                  border: 'none',
                  cursor: 'pointer',
                  background: active ? 'var(--card-surface)' : 'transparent',
                  color: active ? 'var(--text-primary)' : 'var(--text-on-grad)',
                  boxShadow: active ? 'var(--shadow-soft)' : 'none',
                }}
              >
                {t}
              </button>
            )
          })}
        </div>
      </header>

      {/* カード選択（ベージュ + ピンク） */}
      <section style={{ padding: '20px 18px 0' }}>
        <p className="ax-text-secondary" style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
          Pay from
        </p>
        <div className="flex" style={{ gap: 14, overflowX: 'auto', paddingBottom: 4 }}>
          <PayCard tone="warm" brand="Premium" number="4821" balance="$8,240.00" selected />
          <PayCard tone="pink" brand="Savings" number="0934" balance="$4,240.50" />
          <AddCard />
        </div>
      </section>

      {/* Send to */}
      <section style={{ padding: '24px 18px 0' }}>
        <p className="ax-text-primary" style={{ fontSize: 18, fontWeight: 800, marginBottom: 12 }}>Send to</p>

        {/* 検索バー */}
        <div
          className="ax-card-surface ax-r-btn ax-shadow-soft flex items-center gap-3"
          style={{ padding: '13px 16px' }}
        >
          <Search className="h-5 w-5 ax-text-secondary" />
          <input
            placeholder="Search name or @handle"
            className="ax-text-primary"
            style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontSize: 14 }}
          />
        </div>

        {/* 連絡先リスト */}
        <div style={{ marginTop: 18 }}>
          {CONTACTS.map((c) => (
            <div key={c.name} className="flex items-center gap-3" style={{ padding: '11px 4px' }}>
              <span
                className={c.tone === 'warm' ? 'ax-card-warm' : 'ax-card-pink'}
                style={{
                  width: 46,
                  height: 46,
                  borderRadius: 16,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 800,
                }}
              >
                <span className={c.tone === 'warm' ? 'ax-accent-yellow' : 'ax-accent-pink'}>{c.initial}</span>
              </span>
              <div style={{ flex: 1 }}>
                <p className="ax-text-primary" style={{ fontSize: 15, fontWeight: 700 }}>{c.name}</p>
                <p className="ax-text-secondary" style={{ fontSize: 12 }}>{c.handle}</p>
              </div>
              <button
                className="ax-btn-soft"
                style={{ padding: '8px 16px', fontSize: 13, fontWeight: 700, border: 'none', cursor: 'pointer' }}
              >
                Send
              </button>
            </div>
          ))}
        </div>
      </section>

      <ArobixBottomNav />
    </div>
  )
}

function PayCard({
  tone,
  brand,
  number,
  balance,
  selected,
}: {
  tone: 'warm' | 'pink'
  brand: string
  number: string
  balance: string
  selected?: boolean
}) {
  return (
    <div
      className={`${tone === 'warm' ? 'ax-card-warm' : 'ax-card-pink'} ax-r-card ax-shadow-card`}
      style={{
        minWidth: 200,
        padding: 18,
        outline: selected ? '2.5px solid var(--accent-purple)' : 'none',
        outlineOffset: 2,
      }}
    >
      <div className="flex items-center justify-between">
        <span className="ax-text-primary" style={{ fontSize: 13, fontWeight: 700 }}>{brand}</span>
        <span
          className="ax-r-pill"
          style={{ width: 26, height: 18, background: tone === 'warm' ? 'var(--accent-yellow)' : 'var(--accent-pink)', opacity: 0.85 }}
        />
      </div>
      <p className="ax-text-secondary" style={{ marginTop: 18, fontSize: 12, letterSpacing: '0.16em' }}>
        ••••  {number}
      </p>
      <p className="ax-text-primary" style={{ marginTop: 8, fontSize: 18, fontWeight: 800 }}>{balance}</p>
    </div>
  )
}

function AddCard() {
  return (
    <button
      className="ax-r-card flex flex-col items-center justify-center gap-2"
      style={{
        minWidth: 110,
        border: '2px dashed rgba(27,26,35,0.18)',
        background: 'transparent',
        cursor: 'pointer',
        color: 'var(--text-secondary)',
      }}
    >
      <Plus className="h-6 w-6" />
      <span style={{ fontSize: 12, fontWeight: 600 }}>Add card</span>
    </button>
  )
}
