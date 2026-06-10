// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAccount, useConnect, useDisconnect } from 'wagmi'
import { injected } from 'wagmi/connectors'
import { usePrivy, useWallets } from '@privy-io/react-auth'
import { ethers } from 'ethers'
import { SUPPORTED_CHAIN_IDS } from '@/lib/web3/config'

type EthereumProvider = ethers.Eip1193Provider & {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>
}

// window.ethereum はローカルキャストで参照する。
// `declare global { Window.ethereum }` で拡張すると、@privy-io/react-auth 依存が
// ambient 宣言する `Window.ethereum: any` と衝突する（TS2717）ため避ける。
function getInjectedEthereum(): EthereumProvider | undefined {
  if (typeof window === 'undefined') return undefined
  return (window as unknown as { ethereum?: EthereumProvider }).ethereum
}

// PrivyRootClient と「完全に同一」のゲート。Privy 未設定時は PrivyProvider が
// 描画されないため、ここで usePrivy / useWallets を呼ぶと context 不在で throw する。
// このフラグは build-time の env 定数 = runtime で不変 → 条件付き hook 呼び出しでも
// 呼び出し順序は常に同一になり rules-of-hooks の実害は無い。
const PRIVY_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_PRIVY_APP_ID &&
    process.env.NEXT_PUBLIC_PRIVY_APP_ID !== 'clplaceholder000000000000000000000',
)

/** Privy が返す chainId "eip155:84532" / "84532" を数値へ正規化（不能なら null）。 */
function parsePrivyChainId(chainIdStr: string | undefined): number | null {
  if (!chainIdStr) return null
  const part = chainIdStr.includes(':') ? chainIdStr.split(':')[1] : chainIdStr
  const num = Number.parseInt(part, 10)
  return Number.isNaN(num) ? null : num
}

interface PrivyBridge {
  /** embedded wallet アドレス（0x...）。無ければ null。 */
  address: string | null
  /** embedded wallet の chainId（数値）。 */
  chainId: number | null
  /** Privy embedded wallet が存在するか。 */
  hasEmbedded: boolean
  /** embedded wallet の EIP-1193 provider を取得（署名用）。 */
  getEmbeddedProvider: () => Promise<unknown | null>
  /** Privy セッション logout。 */
  logout: () => void
}

const NULL_BRIDGE: PrivyBridge = {
  address: null,
  chainId: null,
  hasEmbedded: false,
  getEmbeddedProvider: async () => null,
  logout: () => {},
}

/**
 * Privy embedded wallet の識別情報・署名 provider・logout を一箇所に集約する内部 hook。
 * PrivyProvider が存在する（PRIVY_CONFIGURED）ツリーでのみ呼ばれる前提。
 */
function usePrivyBridge(): PrivyBridge {
  const { logout } = usePrivy()
  const { wallets } = useWallets()

  const embedded = wallets.find((w) => w.walletClientType === 'privy') ?? null

  const getEmbeddedProvider = useCallback(async () => {
    if (!embedded) return null
    return embedded.getEthereumProvider()
  }, [embedded])

  return {
    address: (embedded?.address as string | undefined) ?? null,
    chainId: parsePrivyChainId(embedded?.chainId),
    hasEmbedded: Boolean(embedded),
    getEmbeddedProvider,
    logout,
  }
}

export function useWallet() {
  // wagmi（injected / 外部ウォレット）は常にツリーに存在する。
  const { address: injAddress, chainId: injChainId, isConnected: injConnected } = useAccount()
  const { connect } = useConnect()
  const { disconnect } = useDisconnect()

  // Privy embedded wallet（LINE / email / SNS ログイン経由）。
  // PRIVY_CONFIGURED は build-time 定数のため、この条件付き呼び出しは呼び出し順序を変えない。
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const privy = PRIVY_CONFIGURED ? usePrivyBridge() : NULL_BRIDGE

  const [provider, setProvider] = useState<ethers.BrowserProvider | null>(null)
  const [signer, setSigner] = useState<ethers.Signer | null>(null)

  // 識別/表示: injected を最優先し、無ければ Privy embedded をフォールバック。
  const address = injAddress ?? privy.address ?? null
  const chainId = injChainId ?? privy.chainId ?? null
  const isConnected = injConnected || privy.hasEmbedded

  const isCorrectChain = chainId != null && SUPPORTED_CHAIN_IDS.includes(chainId)

  // 署名: injected は window.ethereum、無ければ Privy embedded の EIP-1193 provider から生成。
  useEffect(() => {
    let cancelled = false

    async function build() {
      // 1) injected（MetaMask 等）優先
      const injectedEth = getInjectedEthereum()
      if (injConnected && injectedEth) {
        const p = new ethers.BrowserProvider(injectedEth)
        const s = await p.getSigner().catch(() => null)
        if (!cancelled) {
          setProvider(p)
          setSigner(s)
        }
        return
      }

      // 2) Privy embedded wallet
      if (privy.hasEmbedded) {
        try {
          const eip1193 = await privy.getEmbeddedProvider()
          if (!eip1193) {
            if (!cancelled) {
              setProvider(null)
              setSigner(null)
            }
            return
          }
          const p = new ethers.BrowserProvider(eip1193 as unknown as ethers.Eip1193Provider)
          const s = await p.getSigner().catch(() => null)
          if (!cancelled) {
            setProvider(p)
            setSigner(s)
          }
          return
        } catch {
          if (!cancelled) {
            setProvider(null)
            setSigner(null)
          }
          return
        }
      }

      // 3) どちらも無し
      if (!cancelled) {
        setProvider(null)
        setSigner(null)
      }
    }

    void build()
    return () => {
      cancelled = true
    }
    // privy オブジェクト全体ではなく安定したメンバーのみを依存に取る。
    // privy は毎レンダー新しい参照になるため、全体を入れると effect が無限再実行になる。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [injConnected, injAddress, privy.hasEmbedded, privy.getEmbeddedProvider])

  const connectWallet = useCallback(() => {
    connect({ connector: injected() })
  }, [connect])

  const disconnectWallet = useCallback(() => {
    disconnect()
    setProvider(null)
    setSigner(null)
    // embedded wallet 接続中は Privy セッションも終了する（= 実質ログアウト）。
    if (privy.hasEmbedded) privy.logout()
  }, [disconnect, privy])

  const switchToBaseSepolia = useCallback(async () => {
    const eth = getInjectedEthereum()
    if (!eth) return
    try {
      await eth.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0x14a34' }], // Base Sepolia = 84532
      })
    } catch {
      await eth.request({
        method: 'wallet_addEthereumChain',
        params: [{
          chainId: '0x14a34',
          chainName: 'Base Sepolia',
          rpcUrls: ['https://sepolia.base.org'],
          nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 },
          blockExplorerUrls: ['https://sepolia.basescan.org'],
        }],
      })
    }
  }, [])

  const switchToBase = useCallback(async () => {
    const eth = getInjectedEthereum()
    if (!eth) return
    try {
      await eth.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0x2105' }], // Base = 8453
      })
    } catch {
      await eth.request({
        method: 'wallet_addEthereumChain',
        params: [{
          chainId: '0x2105',
          chainName: 'Base',
          rpcUrls: ['https://mainnet.base.org'],
          nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 },
          blockExplorerUrls: ['https://basescan.org'],
        }],
      })
    }
  }, [])

  const switchToOptimism = useCallback(async () => {
    const eth = getInjectedEthereum()
    if (!eth) return
    try {
      await eth.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0xa' }], // Optimism = 10
      })
    } catch {
      await eth.request({
        method: 'wallet_addEthereumChain',
        params: [{
          chainId: '0xa',
          chainName: 'Optimism',
          rpcUrls: ['https://mainnet.optimism.io'],
          nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 },
          blockExplorerUrls: ['https://optimistic.etherscan.io'],
        }],
      })
    }
  }, [])

  const switchToMainnet = useCallback(async () => {
    const eth = getInjectedEthereum()
    if (!eth) return
    await eth.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: '0x1' }], // Ethereum Mainnet = 1
    })
  }, [])

  return {
    address,
    chainId,
    isConnected,
    isCorrectChain,
    connect: connectWallet,
    disconnect: disconnectWallet,
    switchToBaseSepolia,
    switchToBase,
    switchToOptimism,
    switchToMainnet,
    provider,
    signer,
  }
}
