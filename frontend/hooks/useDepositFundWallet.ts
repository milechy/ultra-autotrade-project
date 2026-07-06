// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback, useState } from 'react'
import { useFundWallet } from '@privy-io/react-auth'
import { base, baseSepolia } from 'wagmi/chains'
import { useWallet } from '@/hooks/useWallet'
import { useEffectiveWalletAddress } from '@/hooks/useEffectiveWalletAddress'
import { track, EV } from '@/lib/posthog'

interface UseDepositFundWalletOptions {
  /** fundWallet 終了時（成功・キャンセル問わず）に呼ぶ副作用。残高再取得等に使う。 */
  onSettled?: () => void
}

// PrivyRootClient.tsx と同じ判定（build-time 定数のため条件付き hook 呼び出しでも
// rules-of-hooks の実害は無い — useWallet.ts の PRIVY_CONFIGURED と同じ理屈）。
// Privy App ID 未設定環境では PrivyRootClient が <PrivyProvider> 自体をツリーに
// マウントしないため、ここで useFundWallet() を無条件に呼ぶと
// "Cannot read properties of undefined (reading 'current')" で落ちる
// （AwaitingFundsCard 等が pending 提案の到着だけで自動マウントするため、
// DepositPanel の「ユーザーがボタンを押すまで遅延マウント」より露見しやすい）。
const PRIVY_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_PRIVY_APP_ID &&
    process.env.NEXT_PUBLIC_PRIVY_APP_ID !== 'clplaceholder000000000000000000000',
)

/**
 * Privy fundWallet() の起動ロジックを一箇所に集約する。
 * DepositPanel.tsx の入金タブ・提案カード内の残高不足インライン導線・署名シートの
 * 入金導線のいずれからも同じ挙動（chain 判定・エラーハンドリング・PostHog計測）で呼べるようにする。
 */
export function useDepositFundWallet(options: UseDepositFundWalletOptions = {}) {
  const { onSettled } = options
  const { chainId } = useWallet()
  const { address } = useEffectiveWalletAddress()
  const [isFunding, setIsFunding] = useState(false)

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const fundWalletBridge = PRIVY_CONFIGURED
    ? useFundWallet({
        onUserExited: () => {
          setIsFunding(false)
          onSettled?.()
        },
      })
    : null

  const trigger = useCallback(
    async (amountUsdcHint?: number) => {
      if (!address || !fundWalletBridge) return
      track(EV.DEPOSIT_FUND)
      setIsFunding(true)
      try {
        await fundWalletBridge.fundWallet({
          address,
          options: {
            chain: chainId === 84532 ? baseSepolia : base,
            amount: amountUsdcHint && amountUsdcHint > 0 ? amountUsdcHint.toFixed(2) : '200',
            asset: 'USDC',
          },
        })
      } catch (e) {
        if (e instanceof Error && !e.message.toLowerCase().includes('exit')) {
          // ユーザーキャンセル以外のエラーはコンソールに記録（UI は onUserExited で復旧）
          console.error('[useDepositFundWallet] fundWallet error:', e.message)
        }
      } finally {
        setIsFunding(false)
        onSettled?.()
      }
    },
    [address, chainId, fundWalletBridge, onSettled],
  )

  return { trigger, isFunding, address }
}
