'use client'

import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * web3modal 初期化エラーをキャッチし、ページ全体のクラッシュを防ぐ。
 * エラー時はウォレット機能なしで子コンポーネントをそのまま表示する。
 */
export class WalletErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error) {
    console.warn('[WalletErrorBoundary] web3modal init error (non-fatal):', error.message)
  }

  render() {
    // エラー時もページ本体は表示する（ウォレット機能のみ無効化）
    return this.props.children
  }
}
