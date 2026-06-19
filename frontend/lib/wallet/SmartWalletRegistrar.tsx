'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/lib/wallet/SmartWalletRegistrar.tsx
// Privy Smart Wallet (SCW) が用意でき次第、その address を backend に自動登録する (slice4b)。
// SmartWalletsProvider 配下にマウントする（useSmartWallets を使うため）。描画はしない。

import { useEffect, useRef } from 'react'
import { usePrivy } from '@privy-io/react-auth'
import { useSmartWallets } from '@privy-io/react-auth/smart-wallets'
import { getAuthToken } from '@/lib/auth/token-key'
import { registerSmartWallet } from '@/lib/api/smart-wallet'

export function SmartWalletRegistrar(): null {
  const { authenticated } = usePrivy()
  const { client } = useSmartWallets()
  // 登録済みアドレスを記録し、同一アドレスの再 POST を抑止する（backend も冪等だが無駄打ち回避）。
  const registeredRef = useRef<string | null>(null)

  useEffect(() => {
    const address = client?.account?.address
    const token = getAuthToken()
    if (!address || !token) return
    if (registeredRef.current === address) return
    registeredRef.current = address
    // 失敗時は ref を戻して次回再試行可能にする（fail-open: UI は止めない）。
    registerSmartWallet(address, token)
      .then((res) => {
        if (!res.ok) registeredRef.current = null
      })
      .catch(() => {
        registeredRef.current = null
      })
  }, [client, authenticated])

  return null
}
