'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React from 'react'
import { useTranslations } from 'next-intl'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

// ─── Types ────────────────────────────────────────────────────────────────────

type TranslateFn = (key: string) => string

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

interface ErrorBoundaryClassProps {
  children: React.ReactNode
  fallback?: React.ReactNode
  t: TranslateFn
}

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

// ─── Class component (receives t as prop) ─────────────────────────────────────

class ErrorBoundaryClass extends React.Component<
  ErrorBoundaryClassProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryClassProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  render() {
    const { t } = this.props
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <Alert variant="destructive" className="m-4">
          <AlertTitle>{t('title')}</AlertTitle>
          <AlertDescription>
            <p className="mb-2">{this.state.error?.message}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => this.setState({ hasError: false })}
            >
              {t('retry')}
            </Button>
          </AlertDescription>
        </Alert>
      )
    }

    return this.props.children
  }
}

// ─── Public export: function component wraps class with translation hook ───────

export function ErrorBoundary({ children, fallback }: ErrorBoundaryProps) {
  const t = useTranslations('SharedErrorBoundary')
  return (
    <ErrorBoundaryClass t={t as TranslateFn} fallback={fallback}>
      {children}
    </ErrorBoundaryClass>
  )
}
