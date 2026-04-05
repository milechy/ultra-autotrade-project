'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/user/_components/UserErrorBoundary.tsx
// Error boundary for /user/* pages.
// Catches unhandled React render errors (including 401-triggered crashes)
// and shows a graceful "session expired" UI instead of a blank crash screen.

import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export class UserErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center space-y-4">
            <p className="text-lg text-zinc-300">セッションが切れました</p>
            <a href="/login" className="text-blue-400 underline text-sm">
              再ログインしてください
            </a>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
