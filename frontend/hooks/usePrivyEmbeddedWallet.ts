// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

/**
 * usePrivyEmbeddedWallet
 * ----------------------
 * P1 (privy-embedded-wallet-mvp):
 * Privy `usePrivy()` から `user.linkedAccounts` を走査して embedded wallet を
 * 取り出し、viem の WalletClient を生成して返す hook。
 *
 * - chain は Base mainnet (8453) / Base Sepolia (84532) を切り替え可能。
 *   `NEXT_PUBLIC_DEFAULT_CHAIN_ID` を起動時 chain として採用し、
 *   `switchChain(chainId)` で実行時に切り替えられる。
 * - RPC URL は `NEXT_PUBLIC_BASE_RPC_URL` (base) /
 *   `NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL` (baseSepolia) から取得。
 * - 未認証 / embedded wallet 未付与 / Privy 未設定環境では
 *   `{ address: null, walletClient: null, isReady: false }` を返す。
 *
 * 追加 API (P1 拡張):
 * - `signMessage(message: string): Promise<Hex>` — Privy embedded wallet 経由で
 *   personal_sign を実行するヘルパー。
 * - `getProvider(): EIP1193Provider | null` — `useWallets()` から Privy embedded wallet の
 *   EIP-1193 provider を解決して返す (transaction 送信や ethers wrap に流用可能)。
 * - `switchChain(chainId): Promise<void>` — Privy wallet の chain を切り替える。
 *
 * 例外は下記のいずれかに正規化される:
 *   - `WalletNotReadyError`: 認証未完了 / embedded wallet 未取得 / provider 解決失敗
 *   - `WrongChainError`: 想定外 chain (例えば mainnet 期待で sepolia 接続) を検出
 */

import { useCallback, useMemo, useState } from 'react'
import { usePrivy, useWallets } from '@privy-io/react-auth'
import { base, baseSepolia } from 'viem/chains'
import {
  createWalletClient,
  custom,
  http,
  type Address,
  type Chain,
  type Hex,
  type WalletClient,
} from 'viem'

const BASE_RPC_URL = process.env.NEXT_PUBLIC_BASE_RPC_URL || ''
const BASE_SEPOLIA_RPC_URL = process.env.NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL || ''

const DEFAULT_CHAIN_ID = parseInt(
  process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453',
  10,
)

const SUPPORTED_CHAINS: Record<number, Chain> = {
  [base.id]: base,
  [baseSepolia.id]: baseSepolia,
}

function rpcUrlForChain(chainId: number): string {
  if (chainId === baseSepolia.id) return BASE_SEPOLIA_RPC_URL
  return BASE_RPC_URL
}

/**
 * EIP-1193 provider 最小型 (viem `custom` transport が要求する形に合わせる).
 * Privy `useWallets()[i].getEthereumProvider()` の戻り値はこの型と互換。
 */
export interface EIP1193Provider {
  request(args: { method: string; params?: unknown[] | object }): Promise<unknown>
}

/**
 * Embedded wallet が ready でない (= 認証未完了 / provider 解決失敗) 際に投げる。
 */
export class WalletNotReadyError extends Error {
  constructor(message = 'Privy embedded wallet is not ready') {
    super(message)
    this.name = 'WalletNotReadyError'
  }
}

/**
 * 期待 chain と実 chain が異なる際に投げる (例: mainnet 期待で sepolia 接続).
 */
export class WrongChainError extends Error {
  readonly expected: number
  readonly actual: number | null
  constructor(expected: number, actual: number | null) {
    super(
      `Wrong chain: expected ${expected}, got ${actual === null ? 'unknown' : actual}`,
    )
    this.name = 'WrongChainError'
    this.expected = expected
    this.actual = actual
  }
}

export interface PrivyEmbeddedWalletState {
  /** Embedded wallet の checksum address (未付与時 null) */
  address: Address | null
  /** viem WalletClient (現在 chain ベース、未付与時 null) */
  walletClient: WalletClient | null
  /** 認証済み & embedded wallet 取得済みなら true */
  isReady: boolean
  /** 現在の chain id (例: 8453). 解決前は null. */
  chainId: number | null
  /** Privy embedded wallet 経由で personal_sign を実行する */
  signMessage: (message: string) => Promise<Hex>
  /** Privy wallet の EIP-1193 provider (transaction 送信等に利用) */
  getProvider: () => EIP1193Provider | null
  /** Privy wallet の chain を switch する (Base ↔ Base Sepolia) */
  switchChain: (chainId: number) => Promise<void>
}

/** Privy `wallet.chainId` ("eip155:8453" or "8453") を数値に正規化 */
function parsePrivyChainId(chainIdStr: string | undefined): number | null {
  if (!chainIdStr) return null
  const str = chainIdStr.includes(':') ? chainIdStr.split(':')[1] : chainIdStr
  const num = parseInt(str, 10)
  return Number.isNaN(num) ? null : num
}

/**
 * `usePrivy().user.linkedAccounts` から Privy 製の embedded wallet を 1 件返す。
 * Embedded wallet の判定基準は `type === 'wallet'` かつ `walletClientType === 'privy'`。
 */
function pickEmbeddedWalletAddress(
  linkedAccounts: ReadonlyArray<unknown> | undefined,
): Address | null {
  if (!linkedAccounts) return null
  for (const account of linkedAccounts) {
    if (!account || typeof account !== 'object') continue
    const acct = account as Record<string, unknown>
    if (acct.type !== 'wallet') continue
    if (acct.walletClientType !== 'privy') continue
    const addr = acct.address
    if (typeof addr === 'string' && addr.startsWith('0x')) {
      return addr as Address
    }
  }
  return null
}

/**
 * `useWallets()` の中から Privy embedded wallet (walletClientType === 'privy') を
 * 1 件取り出す。
 */
interface PrivyConnectedWallet {
  address: string
  walletClientType?: string
  chainId?: string
  getEthereumProvider: () => Promise<EIP1193Provider>
  switchChain?: (chainId: number) => Promise<void>
}

function pickEmbeddedWallet(
  wallets: ReadonlyArray<unknown> | undefined,
): PrivyConnectedWallet | null {
  if (!wallets) return null
  for (const w of wallets) {
    if (!w || typeof w !== 'object') continue
    const wl = w as Record<string, unknown>
    if (wl.walletClientType !== 'privy') continue
    if (typeof wl.getEthereumProvider !== 'function') continue
    return wl as unknown as PrivyConnectedWallet
  }
  return null
}

export function usePrivyEmbeddedWallet(): PrivyEmbeddedWalletState {
  const { ready, authenticated, user } = usePrivy()
  const { wallets } = useWallets()

  const address = useMemo<Address | null>(() => {
    if (!ready || !authenticated || !user) return null
    return pickEmbeddedWalletAddress(user.linkedAccounts)
  }, [ready, authenticated, user])

  const embeddedWallet = useMemo<PrivyConnectedWallet | null>(() => {
    return pickEmbeddedWallet(wallets)
  }, [wallets])

  // 現在 chain は Privy embedded wallet の chainId を優先、
  // 取得できなければ env 由来の DEFAULT_CHAIN_ID にフォールバック。
  const detectedChainId = useMemo<number | null>(() => {
    if (embeddedWallet) {
      const parsed = parsePrivyChainId(embeddedWallet.chainId)
      if (parsed !== null) return parsed
    }
    return DEFAULT_CHAIN_ID
  }, [embeddedWallet])

  // switchChain で上書きしたい場合のローカル state。null の間は detectedChainId を使う。
  const [overrideChainId, setOverrideChainId] = useState<number | null>(null)
  const chainId = overrideChainId ?? detectedChainId

  const walletClient = useMemo<WalletClient | null>(() => {
    if (!address) return null
    if (chainId === null) return null
    const chain = SUPPORTED_CHAINS[chainId]
    if (!chain) {
      // eslint-disable-next-line no-console
      console.warn(
        `[usePrivyEmbeddedWallet] Unsupported chainId=${chainId} — WalletClient will be null`,
      )
      return null
    }
    const rpc = rpcUrlForChain(chainId)
    if (!rpc) {
      // eslint-disable-next-line no-console
      console.warn(
        `[usePrivyEmbeddedWallet] RPC URL not set for chainId=${chainId} — WalletClient will be null`,
      )
      return null
    }
    return createWalletClient({
      account: address,
      chain,
      transport: http(rpc),
    })
  }, [address, chainId])

  const getProvider = useCallback((): EIP1193Provider | null => {
    if (!embeddedWallet) return null
    // getEthereumProvider() is async; we cache nothing here — callers awaiting
    // the underlying call should use signMessage / wrap via wallet.getEthereumProvider().
    // For sync API we return a Proxy-like provider that defers to it on first request.
    return {
      request: async (args) => {
        const real = await embeddedWallet.getEthereumProvider()
        return real.request(args)
      },
    }
  }, [embeddedWallet])

  const signMessage = useCallback(
    async (message: string): Promise<Hex> => {
      if (!address || !embeddedWallet) {
        throw new WalletNotReadyError()
      }
      let provider: EIP1193Provider
      try {
        provider = await embeddedWallet.getEthereumProvider()
      } catch (err) {
        throw new WalletNotReadyError(
          `Failed to resolve EIP-1193 provider: ${(err as Error).message}`,
        )
      }
      // viem `custom` transport を経由して personal_sign を呼ぶ。
      // 直接 provider.request するより type 整合性が取りやすい。
      const chain = chainId !== null ? SUPPORTED_CHAINS[chainId] : undefined
      const client = createWalletClient({
        account: address,
        chain,
        transport: custom(provider),
      })
      const sig = await client.signMessage({
        account: address,
        message,
      })
      return sig as Hex
    },
    [address, embeddedWallet, chainId],
  )

  const switchChain = useCallback(
    async (next: number): Promise<void> => {
      if (!embeddedWallet) {
        throw new WalletNotReadyError(
          'Embedded wallet not ready — cannot switch chain',
        )
      }
      if (!(next in SUPPORTED_CHAINS)) {
        throw new WrongChainError(next, parsePrivyChainId(embeddedWallet.chainId))
      }
      if (typeof embeddedWallet.switchChain !== 'function') {
        throw new WalletNotReadyError(
          'Embedded wallet does not expose switchChain — Privy SDK version mismatch?',
        )
      }
      await embeddedWallet.switchChain(next)
      setOverrideChainId(next)
    },
    [embeddedWallet],
  )

  return {
    address,
    walletClient,
    isReady: ready && authenticated && address !== null,
    chainId,
    signMessage,
    getProvider,
    switchChain,
  }
}

export default usePrivyEmbeddedWallet
