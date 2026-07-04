// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useWallet } from '@/hooks/useWallet'
import { useLinkedWalletAddress } from '@/hooks/useLinkedWalletAddress'

export interface EffectiveWalletAddress {
  /** 残高・入金先・表示に使うべきアドレス。smart_wallet_address 優先、無ければ EOA。 */
  address: string | null
  /** true なら address は Smart Wallet (ERC-4337)。false なら EOA。 */
  isSmartWallet: boolean
  /** Privy embedded wallet 等の EOA アドレス（署名 provider の識別に使う場合用）。 */
  eoaAddress: string | null
  loading: boolean
}

/**
 * Aave 実行の実体（backend/app/proposals/router.py の smart_wallet_address 優先ロジック、
 * submit_partner_tx の UserOp sender==smart_wallet_address 検証）と一致する「実効アドレス」
 * を解決する。署名は常に useWallet() の signer（EOA 鍵）で行うため signer は変更しない。
 *
 * smart_wallet_address 未設定（EOA のみのユーザー）の場合は useWallet().address にフォール
 * バックし、従来どおり EOA を実効アドレスとして扱う。
 */
export function useEffectiveWalletAddress(): EffectiveWalletAddress {
  const { address: eoaAddress } = useWallet()
  const { smartWalletAddress, state } = useLinkedWalletAddress(true)

  const isSmartWallet = Boolean(smartWalletAddress)
  const address = smartWalletAddress ?? eoaAddress ?? null

  return {
    address,
    isSmartWallet,
    eoaAddress,
    loading: state === 'loading',
  }
}
