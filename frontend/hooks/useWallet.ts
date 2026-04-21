// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAccount, useConnect, useDisconnect } from 'wagmi'
import { injected } from 'wagmi/connectors'
import { ethers } from 'ethers'
import { SUPPORTED_CHAIN_IDS } from '@/lib/web3/config'

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

  const isCorrectChain = chainId != null && SUPPORTED_CHAIN_IDS.includes(chainId)

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

  const switchToBaseSepolia = useCallback(async () => {
    if (typeof window === 'undefined' || !window.ethereum) return
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0x14a34' }], // Base Sepolia = 84532
      })
    } catch {
      await window.ethereum.request({
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
    if (typeof window === 'undefined' || !window.ethereum) return
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0x2105' }], // Base = 8453
      })
    } catch {
      await window.ethereum.request({
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
    if (typeof window === 'undefined' || !window.ethereum) return
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0xa' }], // Optimism = 10
      })
    } catch {
      await window.ethereum.request({
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
    if (typeof window === 'undefined' || !window.ethereum) return
    await window.ethereum.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: '0x1' }], // Ethereum Mainnet = 1
    })
  }, [])

  return {
    address: address ?? null,
    chainId: chainId ?? null,
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
