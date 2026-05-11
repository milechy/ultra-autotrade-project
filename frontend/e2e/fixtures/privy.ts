// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// F-17/8: Privy test token integration for E2E (Asana 1214628970352813).
//
// 目的:
//   - Lane G の 422 経路だけだった /auth/wallet/link を、viem の実 EIP-191 署名で
//     200 経路まで E2E で踏破できるようにする。
//   - UserHeader の wallet badge (= wagmi useAccount 由来) が「接続済み」になった
//     状態を Playwright で安定再現する。
//
// 設計方針:
//   - Privy SDK 自体は driver 不可能 (auth.privy.io の iframe / modal は安定操作不可)。
//     よって本ファイルでは Privy には触れず、viem + wagmi の lower-level に閉じる。
//   - 秘密鍵は backend/tests/test_auth_wallet_link.py:38 と同値の公開鍵 (本番資産 0)。
//     env `E2E_TEST_PRIVATE_KEY` で上書き可。

import type { Page } from '@playwright/test'
import { privateKeyToAccount, type PrivateKeyAccount } from 'viem/accounts'

/**
 * テスト用秘密鍵 (本番資産価値ゼロ — backend テストと同値で意図的に互換)。
 * E2E_TEST_PRIVATE_KEY env で上書き可能。
 */
export const TEST_PRIVATE_KEY: `0x${string}` =
  (process.env.E2E_TEST_PRIVATE_KEY as `0x${string}` | undefined) ??
  '0x4c0883a69102937d6231471b5dbb6e538eba2ef158d8b8b75f21c8f4d9c3f5a2'

/** viem privateKeyToAccount のキャッシュ済シングルトン */
let _cachedAccount: PrivateKeyAccount | null = null

export function getTestAccount(): PrivateKeyAccount {
  if (_cachedAccount == null) {
    _cachedAccount = privateKeyToAccount(TEST_PRIVATE_KEY)
  }
  return _cachedAccount
}

export interface SignedWalletLinkPayload {
  address: string
  signature: string
  message: string
}

/**
 * POST /auth/wallet/link のリクエスト body を viem で署名して返す。
 *
 * バックエンドは `eth_account.recover_message(encode_defunct(text=message), signature=signature)`
 * で復元するため、viem の `signMessage({ message: raw_text })` (EIP-191 personal_sign) と互換。
 */
export async function signWalletLinkPayload(
  message?: string,
  account?: PrivateKeyAccount,
): Promise<SignedWalletLinkPayload> {
  const acc = account ?? getTestAccount()
  const msg = message ?? `Ultra AutoTrade: link ${new Date().toISOString()}`
  const signature = await acc.signMessage({ message: msg })
  return {
    address: acc.address,
    signature,
    message: msg,
  }
}

export interface SetupConnectedWalletResult {
  address: string
  chainId: number
}

/**
 * wagmi の `injected` connector に接続済の状態をブラウザ側に注入する。
 *
 * 仕組み (page.addInitScript なので page.goto より前に呼ぶこと):
 *   1. window.ethereum を最小限の EIP-1193 互換 stub で差し込む
 *      (eth_chainId / eth_accounts / eth_requestAccounts / wallet_switchEthereumChain を実装)
 *   2. wagmi の localStorage キー `wagmi.store` / `wagmi.recentConnectorId` を
 *      「injected で connected 済」状態でシード
 *   3. wagmi がマウント時に rehydrate → useAccount().isConnected = true
 *
 * 注意: 実署名は本 stub では行わない (UI badge 表示確認のみが目的)。実署名が必要な
 * テストは API レベルで `signWalletLinkPayload()` を使うこと。
 */
export async function setupConnectedWagmiWallet(
  page: Page,
  opts?: { chainId?: number; account?: PrivateKeyAccount },
): Promise<SetupConnectedWalletResult> {
  const account = opts?.account ?? getTestAccount()
  const chainId = opts?.chainId ?? 8453
  const address = account.address

  await page.addInitScript(
    (args: { address: string; chainId: number }) => {
      const chainIdHex = '0x' + args.chainId.toString(16)

      // ── 1. window.ethereum mock (read-only stub) ───────────────────────
      const listeners: Record<string, Array<(...a: unknown[]) => void>> = {}
      const eth = {
        isMetaMask: true,
        chainId: chainIdHex,
        networkVersion: String(args.chainId),
        selectedAddress: args.address,
        on(event: string, handler: (...a: unknown[]) => void) {
          ;(listeners[event] ||= []).push(handler)
          return eth
        },
        removeListener(event: string, handler: (...a: unknown[]) => void) {
          listeners[event] = (listeners[event] ?? []).filter((h) => h !== handler)
          return eth
        },
        async request({
          method,
          params,
        }: {
          method: string
          params?: unknown[]
        }): Promise<unknown> {
          switch (method) {
            case 'eth_chainId':
              return eth.chainId
            case 'net_version':
              return eth.networkVersion
            case 'eth_requestAccounts':
            case 'eth_accounts':
              return [args.address]
            case 'wallet_switchEthereumChain': {
              const p = (params ?? []) as Array<{ chainId: string }>
              const newId = p[0]?.chainId
              if (newId) {
                eth.chainId = newId
                eth.networkVersion = String(parseInt(newId, 16))
                ;(listeners['chainChanged'] ?? []).forEach((h) => h(newId))
              }
              return null
            }
            case 'wallet_addEthereumChain':
              return null
            case 'eth_getBalance':
              return '0xde0b6b3a7640000' // 1 ETH wei
            default:
              return null
          }
        },
      }
      ;(window as unknown as { ethereum: unknown }).ethereum = eth

      // ── 2. wagmi 永続化 storage seeding ─────────────────────────────────
      // wagmi v2/v3 共通: storage key は `wagmi.store` (state.connections は Map)。
      // フォーマット差で hydrate に失敗しても、injected connector は window.ethereum
      // が存在すれば再接続可能なので最悪 useEffect 経由で自動回復する。
      try {
        localStorage.setItem('wagmi.recentConnectorId', JSON.stringify('injected'))
        localStorage.setItem(
          'wagmi.store',
          JSON.stringify({
            state: {
              chainId: args.chainId,
              current: 'injected',
              connections: {
                __type: 'Map',
                value: [
                  [
                    'injected',
                    {
                      accounts: [args.address],
                      chainId: args.chainId,
                      connector: {
                        id: 'injected',
                        name: 'Injected',
                        type: 'injected',
                        uid: 'injected',
                      },
                    },
                  ],
                ],
              },
              status: 'connected',
            },
            version: 2,
          }),
        )
      } catch {
        // localStorage 書込失敗は無視 (Playwright headless では常に成功する想定)
      }
    },
    { address, chainId },
  )

  return { address, chainId }
}
