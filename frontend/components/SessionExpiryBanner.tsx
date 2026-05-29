'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/components/SessionExpiryBanner.tsx
//
// iOS ITP (7日間操作なし) によるセッション消去を事前に警告するバナー。
// useITPGuard が 'warning' または 'itp_expired' を返したときに表示する。
// Privy 再認証は PrivySessionGuard が担当。本コンポーネントは JWT + last_seen のみ。

import { useITPGuard } from '@/hooks/useITPGuard'

export function SessionExpiryBanner() {
  const { sessionState, hoursUntilExpiry } = useITPGuard()

  if (sessionState === 'ok') return null

  const hoursLabel =
    hoursUntilExpiry !== null
      ? `（残り約 ${Math.ceil(hoursUntilExpiry)} 時間）`
      : ''

  const isExpired = sessionState === 'itp_expired'

  return (
    <div
      role="alert"
      data-testid="session-expiry-banner"
      data-state={sessionState}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9998,
        background: isExpired ? '#7c3aed' : '#b45309',
        color: '#fff',
        padding: '10px 16px',
        fontSize: 14,
        textAlign: 'center',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
      }}
    >
      <span>
        {isExpired
          ? 'セッションが期限切れです。再ログインしてください。'
          : `セッションの有効期限が近づいています${hoursLabel}。再ログインで延長できます。`}
      </span>
      <button
        type="button"
        data-testid="session-expiry-reauth-btn"
        onClick={() => {
          if (typeof window !== 'undefined') {
            window.location.href = '/login'
          }
        }}
        style={{
          background: '#fff',
          color: isExpired ? '#7c3aed' : '#b45309',
          border: 'none',
          borderRadius: 4,
          padding: '4px 10px',
          fontSize: 12,
          fontWeight: 600,
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        再ログイン
      </button>
    </div>
  )
}
