'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/user/_components/UserErrorBoundary.tsx
// Error boundary for /user/* pages.
// Catches unhandled React render errors and shows a graceful error UI.
// NOTE: handle401 (in lib/api/client.ts) redirects to /login directly, so
// 401 errors from API calls do NOT reach this boundary.

import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  errorMessage: string | null
}

export class UserErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
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
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center space-y-4 max-w-sm px-4">
            <p className="text-lg text-zinc-300">予期しないエラーが発生しました</p>
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
                ページを再読み込み
              </button>
              <a href="/login" className="text-zinc-500 underline text-xs">
                ログイン画面へ
              </a>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
