'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/user/_components/UserErrorBoundary.tsx
// Error boundary for /user/* pages.
// Catches unhandled React render errors and shows a graceful error UI.
// NOTE: handle401 (in lib/api/client.ts) redirects to /login directly, so
// 401 errors from API calls do NOT reach this boundary.

import { Component, ReactNode } from 'react'
import { useTranslations } from 'next-intl'

// ─── Types ────────────────────────────────────────────────────────────────────

type TranslateFn = (key: string) => string

interface InnerProps {
  children: ReactNode
  t: TranslateFn
}

interface State {
  hasError: boolean
  errorMessage: string | null
}

// ─── Class component (receives t as prop) ─────────────────────────────────────

class UserErrorBoundaryClass extends Component<InnerProps, State> {
  constructor(props: InnerProps) {
    super(props)
    this.state = { hasError: false, errorMessage: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error?.message ?? null }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[UserErrorBoundary] Uncaught error:', error, info.componentStack)
  }

  render() {
    const { t } = this.props
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center space-y-4 max-w-sm px-4">
            <p className="text-lg text-zinc-300">{t('unexpectedError')}</p>
            {this.state.errorMessage && (
              <p className="text-xs text-zinc-500 font-mono break-all">
                {this.state.errorMessage}
              </p>
            )}
            <div className="flex flex-col gap-2 items-center">
              <button
                onClick={() => window.location.reload()}
                className="text-blue-400 underline text-sm"
              >
                {t('reload')}
              </button>
              <a href="/login" className="text-zinc-500 underline text-xs">
                {t('goToLogin')}
              </a>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

// ─── Public export: function component wraps class with translation hook ───────

export function UserErrorBoundary({ children }: { children: ReactNode }) {
  const t = useTranslations('UserErrorBoundary')
  return (
    <UserErrorBoundaryClass t={t as TranslateFn}>
      {children}
    </UserErrorBoundaryClass>
  )
}
