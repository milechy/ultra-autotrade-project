import { createConfig, http } from 'wagmi'
import { arbitrum } from 'wagmi/chains'
import { walletConnect, injected } from 'wagmi/connectors'

export const projectId = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || 'demo-project-id'

export const wagmiConfig = createConfig({
  chains: [arbitrum],
  transports: {
    [arbitrum.id]: http(),
  },
  connectors: [
    walletConnect({ projectId }),
    injected(),
  ],
})
