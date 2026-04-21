// Copyright (c) Ultra AutoTrade. All rights reserved.
import type { Page } from '@playwright/test'

/** Canonical mock address used across wallet tests */
export const MOCK_ADDRESS = '0xAbCd1234567890AbCd1234567890AbCd12345678'

/**
 * Short-format address as rendered by the connect page:
 * `${address.slice(0, 6)}…${address.slice(-4)}`
 */
export const MOCK_ADDRESS_SHORT =
  MOCK_ADDRESS.slice(0, 6) + '…' + MOCK_ADDRESS.slice(-4)

export type WalletMockOptions = {
  /**
   * EIP-155 chain ID the mock reports.
   * Default: 84532 (Base Sepolia)
   */
  chainId?: number
  /**
   * When true, eth_requestAccounts throws a user-rejection error (code 4001).
   * Default: false
   */
  rejectConnect?: boolean
}

/**
 * Injects a minimal EIP-1193-compliant mock into `window.ethereum` **before**
 * the page JavaScript runs.  Must be called before `page.goto()`.
 *
 * The mock handles:
 *   eth_requestAccounts  – returns [MOCK_ADDRESS] (or throws if rejectConnect)
 *   eth_accounts         – returns current accounts
 *   eth_chainId          – returns chainId as hex string
 *   net_version          – returns chainId as decimal string
 *   wallet_switchEthereumChain – updates chainId and fires "chainChanged"
 *   wallet_addEthereumChain    – no-op success
 *   eth_getBalance             – returns 1 ETH in wei
 *
 * wagmi's injected() connector relies on these methods, so clicking the
 * "ウォレットを接続する" button will succeed against this mock.
 */
export async function mockEthereum(
  page: Page,
  options: WalletMockOptions = {}
): Promise<void> {
  const chainId = options.chainId ?? 84532
  const rejectConnect = options.rejectConnect ?? false
  const chainIdHex = '0x' + chainId.toString(16)

  await page.addInitScript(
    (args: { chainIdHex: string; rejectConnect: boolean; mockAddress: string }) => {
      // ---- runs in browser context ----
      const listeners: Record<string, Array<(...a: unknown[]) => void>> = {}
      let connected = false

      const eth = {
        isMetaMask: true,
        selectedAddress: null as string | null,
        chainId: args.chainIdHex,
        networkVersion: String(parseInt(args.chainIdHex, 16)),

        on(event: string, handler: (...a: unknown[]) => void) {
          if (!listeners[event]) listeners[event] = []
          listeners[event].push(handler)
          return eth
        },

        removeListener(event: string, handler: (...a: unknown[]) => void) {
          listeners[event] = (listeners[event] ?? []).filter((h) => h !== handler)
          return eth
        },

        _emit(event: string, ...a: unknown[]) {
          listeners[event]?.forEach((h) => h(...a))
        },

        async request({
          method,
          params,
        }: {
          method: string
          params?: unknown[]
        }): Promise<unknown> {
          switch (method) {
            case 'eth_requestAccounts':
              if (args.rejectConnect) {
                throw Object.assign(new Error('User rejected the request.'), {
                  code: 4001,
                })
              }
              eth.selectedAddress = args.mockAddress
              connected = true
              return [args.mockAddress]

            case 'eth_accounts':
              return connected ? [args.mockAddress] : []

            case 'eth_chainId':
              return eth.chainId

            case 'net_version':
              return eth.networkVersion

            case 'wallet_switchEthereumChain': {
              const p = (params ?? []) as Array<{ chainId: string }>
              const newChainId = p[0]?.chainId
              if (newChainId) {
                eth.chainId = newChainId
                eth.networkVersion = String(parseInt(newChainId, 16))
                // notify wagmi's injected connector
                eth._emit('chainChanged', newChainId)
              }
              return null
            }

            case 'wallet_addEthereumChain':
              return null

            case 'eth_getBalance':
              return '0xde0b6b3a7640000' // 1 ETH in wei

            default:
              return null
          }
        },
      }

      // Attach to window so wagmi's injected() connector picks it up
      ;(window as unknown as Record<string, unknown>).ethereum = eth
      // Expose for test introspection via page.evaluate()
      ;(window as unknown as Record<string, unknown>).__mockEthereum = eth
    },
    { chainIdHex, rejectConnect, mockAddress: MOCK_ADDRESS }
  )
}
