// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAccount, useConnect, useDisconnect } from 'wagmi'
import { injected } from 'wagmi/connectors'
import { ethers } from 'ethers'
import { ARBITRUM_CHAIN_IDS } from '@/lib/web3/config'

type EthereumProvider = ethers.Eip1193Provider & {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>
}

declare global {
  interface Window {
    ethereum?: EthereumProvider
  }
}

export function useWallet() {
  const { address, chainId, isConnected } = useAccount()
  const { connect } = useConnect()
  const { disconnect } = useDisconnect()

  const [provider, setProvider] = useState<ethers.BrowserProvider | null>(null)
  const [signer, setSigner] = useState<ethers.Signer | null>(null)

  const isCorrectChain = chainId != null && ARBITRUM_CHAIN_IDS.includes(chainId)

  // window.ethereum が利用可能なときに BrowserProvider を生成
  useEffect(() => {
    if (!isConnected || typeof window === 'undefined' || !window.ethereum) {
      setProvider(null)
      setSigner(null)
      return
    }
    const ethProvider = new ethers.BrowserProvider(window.ethereum)
    setProvider(ethProvider)
    ethProvider.getSigner().then(setSigner).catch(() => setSigner(null))
  }, [isConnected, address])

  const connectWallet = useCallback(() => {
    connect({ connector: injected() })
  }, [connect])

  const disconnectWallet = useCallback(() => {
    disconnect()
    setProvider(null)
    setSigner(null)
  }, [disconnect])

  const switchToArbitrum = useCallback(async () => {
    if (typeof window === 'undefined' || !window.ethereum) return
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0xa4b1' }], // Arbitrum One = 42161
      })
    } catch {
      // チェーンが未登録の場合は追加
      await window.ethereum.request({
        method: 'wallet_addEthereumChain',
        params: [{
          chainId: '0xa4b1',
          chainName: 'Arbitrum One',
          rpcUrls: ['https://arb1.arbitrum.io/rpc'],
          nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 },
          blockExplorerUrls: ['https://arbiscan.io'],
        }],
      })
    }
  }, [])

  return {
    address: address ?? null,
    chainId: chainId ?? null,
    isConnected,
    isCorrectChain,
    connect: connectWallet,
    disconnect: disconnectWallet,
    switchToArbitrum,
    provider,
    signer,
  }
}
