// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback, useEffect, useState } from 'react'
import { ethers } from 'ethers'
import { useWallet } from '@/hooks/useWallet'
import { ERC20_ABI } from '@/lib/web3/abi/erc20'
import { TOKEN_ADDRESSES, SUPPORTED_CHAINS, getChainKey, DEFAULT_CHAIN } from '@/lib/web3/config'

interface UsdcBalanceState {
  /** USDC 残高（数値）。未取得 / エラー / アドレス無し時は null。 */
  balanceUsd: number | null
  loading: boolean
  error: boolean
  /** 再取得（入金・出金後の更新用）。 */
  refetch: () => void
}

// チェーンキー → トークン / RPC を安全に引く（'optimism' 等 USDC 未定義キーは undefined）。
const TOKENS = TOKEN_ADDRESSES as Record<string, { USDC?: string } | undefined>
const CHAINS = SUPPORTED_CHAINS as Record<string, { rpc?: string } | undefined>

/**
 * ユーザー自身の（非カストディアル）ウォレットの USDC オンチェーン残高を読む。
 *
 * 資金はプラットフォームが保管しない設計のため、これがユーザーの「現在資産」の正となる。
 * 旧実装は /api/user/settings の `balance` を読んでいたが、当該フィールドはバックエンドに
 * 存在せず常に null（= 残高 $0 表示）だった。read-only provider 経由の balanceOf に置換する。
 * balanceOf は署名不要のため signer は使わない。
 */
export function useUsdcBalance(): UsdcBalanceState {
  const { address, chainId } = useWallet()
  const [balanceUsd, setBalanceUsd] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [nonce, setNonce] = useState(0)

  const refetch = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false

    async function read() {
      if (!address) {
        setBalanceUsd(null)
        setError(false)
        return
      }
      // 接続チェーンを優先。不明時は既定チェーン（本番 = Base mainnet）にフォールバック。
      const chainKey = (chainId != null ? getChainKey(chainId) : null) ?? DEFAULT_CHAIN
      const usdc = TOKENS[chainKey]?.USDC
      const rpc = CHAINS[chainKey]?.rpc
      if (!usdc || !rpc) {
        setBalanceUsd(null)
        return
      }
      setLoading(true)
      setError(false)
      try {
        const provider = new ethers.JsonRpcProvider(rpc)
        const erc20 = new ethers.Contract(usdc, ERC20_ABI, provider)
        const [raw, decimals] = await Promise.all([
          erc20.balanceOf(address) as Promise<bigint>,
          erc20.decimals() as Promise<bigint>,
        ])
        if (!cancelled) {
          setBalanceUsd(Number(ethers.formatUnits(raw, decimals)))
        }
      } catch {
        if (!cancelled) {
          setBalanceUsd(null)
          setError(true)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void read()
    return () => {
      cancelled = true
    }
  }, [address, chainId, nonce])

  return { balanceUsd, loading, error, refetch }
}
