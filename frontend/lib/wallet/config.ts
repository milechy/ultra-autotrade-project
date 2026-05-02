// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { createConfig, http } from 'wagmi'
import { arbitrum, base, baseSepolia, mainnet, optimism } from 'wagmi/chains'
import { injected } from 'wagmi/connectors'

export const projectId = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || ''

// Default chain is Base メインネット (8453). Override via NEXT_PUBLIC_DEFAULT_CHAIN_ID. 84532 = Base Sepolia.
const defaultChainId = parseInt(process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453')

const allChains = [baseSepolia, base, arbitrum, optimism, mainnet] as const

// Put the default chain first so wagmi treats it as primary
const sortedChains = [
  ...allChains.filter(c => c.id === defaultChainId),
  ...allChains.filter(c => c.id !== defaultChainId),
] as [typeof allChains[number], ...typeof allChains[number][]]

export const wagmiConfig = createConfig({
  chains: sortedChains,
  transports: {
    [baseSepolia.id]: http(),
    [base.id]: http(),
    [arbitrum.id]: http(),
    [optimism.id]: http(),
    [mainnet.id]: http(),
  },
  connectors: [
    injected(),
  ],
})
