// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// ERC-20 Paymaster client helper (Base, EntryPoint v0.7).
//
// 仕様原文では Paymaster は将来扱いだったが、Q3 reframe で MVP 格上げ。
// ユーザの初回 tx 前にガス額(USDC)を見積もり、承認 UI を経由して
// Paymaster API へ UserOperation を投げる導線をここに集約する。
//
// 想定 Paymaster: Pimlico / Stackup / Alchemy Account Kit (いずれも EntryPoint v0.7 互換)

import { createPublicClient, http } from 'viem'
import { base, baseSepolia } from 'viem/chains'

export type TxHash = `0x${string}`

export interface PaymasterConfig {
  url: string
  apiKey: string
}

export interface TransactionRequest {
  to: `0x${string}`
  data?: `0x${string}`
  value?: bigint
  from?: `0x${string}`
}

/**
 * EIP-4337 v0.7 UserOperation。Paymaster 経由送信時に bundler に渡す形。
 */
export interface UserOperation {
  sender: `0x${string}`
  nonce: bigint
  callData: `0x${string}`
  callGasLimit?: bigint
  verificationGasLimit?: bigint
  preVerificationGas?: bigint
  maxFeePerGas?: bigint
  maxPriorityFeePerGas?: bigint
  /** EntryPoint v0.7: paymaster は paymasterAndData ではなく分割フィールド */
  paymaster?: `0x${string}`
  paymasterVerificationGasLimit?: bigint
  paymasterPostOpGasLimit?: bigint
  paymasterData?: `0x${string}`
  signature?: `0x${string}`
  factory?: `0x${string}`
  factoryData?: `0x${string}`
}

// 最小の WalletClient interface (Privy / wagmi / viem いずれにも適応できるよう緩く)
export interface PaymasterWalletClient {
  account?: { address: `0x${string}` }
  sendTransaction?: (tx: TransactionRequest) => Promise<TxHash>
  /** EIP-4337 v0.7: 署名済み UserOperation を bundler へ送る関数 (Privy / viem AA) */
  sendUserOperation?: (userOp: UserOperation) => Promise<TxHash>
  /** UserOperation の署名 (Privy embedded wallet に存在) */
  signUserOperation?: (userOp: UserOperation) => Promise<`0x${string}`>
}

/** EntryPoint v0.7 公式アドレス (Base mainnet / Base Sepolia 共通) */
export const ENTRY_POINT_V07_ADDRESS =
  '0x0000000071727De22E5E9d8BAf0edAc6f37da032' as const

// ---------------------------------------------------------------------------
// Error classes
// ---------------------------------------------------------------------------

/** Paymaster 由来エラーの基底クラス */
export class PaymasterError extends Error {
  public readonly cause?: unknown
  constructor(message: string, cause?: unknown) {
    super(message)
    this.name = 'PaymasterError'
    this.cause = cause
  }
}

/** Paymaster URL/API key 未設定 or 到達不可 */
export class PaymasterUnavailableError extends PaymasterError {
  constructor(message: string, cause?: unknown) {
    super(message, cause)
    this.name = 'PaymasterUnavailableError'
  }
}

/** ユーザ残高が見積もった USDC ガス代に満たない */
export class InsufficientUsdcError extends PaymasterError {
  public readonly requiredUsdc6dp: bigint
  public readonly currentUsdc6dp: bigint
  constructor(requiredUsdc6dp: bigint, currentUsdc6dp: bigint) {
    super(
      `[paymaster] insufficient USDC: required=${requiredUsdc6dp.toString()} have=${currentUsdc6dp.toString()}`
    )
    this.name = 'InsufficientUsdcError'
    this.requiredUsdc6dp = requiredUsdc6dp
    this.currentUsdc6dp = currentUsdc6dp
  }
}

// ---------------------------------------------------------------------------
// Config helpers
// ---------------------------------------------------------------------------

/**
 * 環境変数から Paymaster の URL / API Key を返す。
 * 値が未設定の場合は空文字を返し、呼び出し側で fallback (Paymaster 無し送信) させる。
 */
export function getPaymasterConfig(): PaymasterConfig {
  const url = process.env.NEXT_PUBLIC_PAYMASTER_URL || ''
  const apiKey = process.env.NEXT_PUBLIC_PAYMASTER_API_KEY || ''
  return { url, apiKey }
}

/**
 * Paymaster が利用可能か (URL/API Key の両方が設定されているか) を返す。
 */
export function isPaymasterEnabled(): boolean {
  const { url, apiKey } = getPaymasterConfig()
  return url.length > 0 && apiKey.length > 0
}

/**
 * USDC (6 decimals, bigint) を画面表示用の数値に変換するヘルパ。
 */
export function formatUsdc6dp(amount: bigint): number {
  // bigint -> number で精度は落ちるが UI 表示用なので許容。
  return Number(amount) / 1_000_000
}

// ---------------------------------------------------------------------------
// Public chain client (viem)
// ---------------------------------------------------------------------------

function getDefaultChain() {
  const id = parseInt(process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453', 10)
  return id === 84532 ? baseSepolia : base
}

/** モジュール内部で使う viem PublicClient (gas / gasPrice 取得用) */
function getPublicClient() {
  const chain = getDefaultChain()
  const rpc =
    chain.id === 84532
      ? process.env.NEXT_PUBLIC_BASE_SEPOLIA_RPC
      : process.env.NEXT_PUBLIC_BASE_MAINNET_RPC
  return createPublicClient({
    chain,
    transport: http(rpc || undefined),
  })
}

// ---------------------------------------------------------------------------
// ETH -> USDC fallback rate
// ---------------------------------------------------------------------------

/**
 * Paymaster API 不通時に使う ETH→USD 換算レート。
 * `NEXT_PUBLIC_ETH_USD_PRICE` で上書き可、未設定なら 3000 USD/ETH。
 */
function getEthUsdPrice(): number {
  const raw = process.env.NEXT_PUBLIC_ETH_USD_PRICE
  const parsed = raw ? Number(raw) : NaN
  if (!Number.isFinite(parsed) || parsed <= 0) return 3000
  return parsed
}

/**
 * gas units × gas price (wei) → USDC(6dp, bigint) のローカル換算。
 * Paymaster API 不通時の fallback。
 */
function ethGasToUsdc6dp(gasUnits: bigint, gasPriceWei: bigint): bigint {
  const ethUsd = getEthUsdPrice()
  // 整数演算で 6dp を維持: (gas * price * usd * 1e6) / 1e18
  // ethUsd は浮動小数の可能性があるので 1e6 倍してから整数化。
  const usdScaled = BigInt(Math.round(ethUsd * 1_000_000)) // USD * 1e6 / ETH
  const numerator = gasUnits * gasPriceWei * usdScaled
  const denominator = 10n ** 18n * 1_000_000n // wei -> ETH (1e18) と USD*1e6 を相殺
  // 結果は USDC * 1e6 (= 6dp)
  return numerator / denominator
}

// ---------------------------------------------------------------------------
// estimateGasInUsdc
// ---------------------------------------------------------------------------

/**
 * tx のガス代を USDC 建てで見積もる。
 *
 * 1) viem `estimateGas` で gas units を出す
 * 2) viem `getGasPrice` で現在のガス価格を取る
 * 3) Paymaster API `/quote` に POST して USDC 単価を取得
 * 4) 失敗時は ETH→USDC 換算で fallback
 *
 * @returns bigint (USDC 6 decimals)
 */
export async function estimateGasInUsdc(
  tx: TransactionRequest
): Promise<bigint> {
  const client = getPublicClient()

  let gasUnits: bigint
  let gasPrice: bigint
  try {
    // viem 2.x の estimateGas は account を要求するが、ここでは tx.from を渡す。
    // from 未指定なら 0 アドレスで概算 (UI 表示用なので許容)。
    const account =
      tx.from ??
      ('0x0000000000000000000000000000000000000000' as `0x${string}`)
    ;[gasUnits, gasPrice] = await Promise.all([
      client.estimateGas({
        account,
        to: tx.to,
        data: tx.data,
        value: tx.value,
      }),
      client.getGasPrice(),
    ])
  } catch (err) {
    // RPC 自体が落ちている場合は安全側 (典型値 200k gas × 0.1 gwei) で概算
    gasUnits = 200_000n
    gasPrice = 100_000_000n // 0.1 gwei (Base は安い)
    // eslint-disable-next-line no-console
    console.warn('[paymaster] estimateGas failed, using fallback gas units:', err)
  }

  const { url, apiKey } = getPaymasterConfig()
  if (url && apiKey) {
    try {
      const res = await fetch(`${url}/quote`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
        },
        body: JSON.stringify({
          userOp: {
            sender: tx.from ?? null,
            callData: tx.data ?? '0x',
          },
          gasUnits: gasUnits.toString(),
          gasPrice: gasPrice.toString(),
          chainId: getDefaultChain().id,
          token: 'USDC',
        }),
      })
      if (res.ok) {
        const body = (await res.json()) as { usdcAmount?: string | number }
        if (body.usdcAmount !== undefined && body.usdcAmount !== null) {
          // API は 6dp の整数文字列を返す想定 (Pimlico/Stackup 仕様に合わせる)
          return BigInt(body.usdcAmount)
        }
      } else {
        // eslint-disable-next-line no-console
        console.warn(
          `[paymaster] /quote returned ${res.status}, falling back to ETH→USDC`
        )
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[paymaster] /quote unreachable, falling back to ETH→USDC:', err)
    }
  }

  // Fallback: gasUnits × gasPrice × ETH_USD_PRICE / 10^18 で USDC 換算
  return ethGasToUsdc6dp(gasUnits, gasPrice)
}

// ---------------------------------------------------------------------------
// sendUserOpWithPaymaster
// ---------------------------------------------------------------------------

interface SponsorResponse {
  // EntryPoint v0.7 分割フィールド
  paymaster?: `0x${string}`
  paymasterData?: `0x${string}`
  paymasterVerificationGasLimit?: string
  paymasterPostOpGasLimit?: string
  // 互換: v0.6 形式を返す Paymaster もあるので受けておく
  paymasterAndData?: `0x${string}`
  // bundler が再見積もりした gas
  callGasLimit?: string
  verificationGasLimit?: string
  preVerificationGas?: string
  maxFeePerGas?: string
  maxPriorityFeePerGas?: string
}

function toBigIntOrUndef(s?: string): bigint | undefined {
  if (s === undefined || s === null || s === '') return undefined
  try {
    return BigInt(s)
  } catch {
    return undefined
  }
}

/**
 * UserOperation を Paymaster 経由で送信する。
 *
 * 1) Paymaster API `/sponsor` に POST → paymaster/paymasterData (v0.7) を取得
 * 2) walletClient.sendUserOperation で bundler に投げる
 * 3) tx hash を返す
 *
 * EntryPoint v0.7 想定。エラー時は PaymasterError 系でラップ。
 */
export async function sendUserOpWithPaymaster(
  walletClient: PaymasterWalletClient,
  userOp: UserOperation
): Promise<TxHash> {
  const { url, apiKey } = getPaymasterConfig()
  if (!url || !apiKey) {
    throw new PaymasterUnavailableError(
      '[paymaster] NEXT_PUBLIC_PAYMASTER_URL / NEXT_PUBLIC_PAYMASTER_API_KEY が未設定です'
    )
  }

  // 1) /sponsor: Paymaster に署名 (paymasterData) を要求
  let sponsor: SponsorResponse
  try {
    const res = await fetch(`${url}/sponsor`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
      },
      body: JSON.stringify({
        userOp: {
          sender: userOp.sender,
          nonce: userOp.nonce.toString(),
          callData: userOp.callData,
          callGasLimit: userOp.callGasLimit?.toString(),
          verificationGasLimit: userOp.verificationGasLimit?.toString(),
          preVerificationGas: userOp.preVerificationGas?.toString(),
          maxFeePerGas: userOp.maxFeePerGas?.toString(),
          maxPriorityFeePerGas: userOp.maxPriorityFeePerGas?.toString(),
          factory: userOp.factory,
          factoryData: userOp.factoryData,
        },
        entryPoint: ENTRY_POINT_V07_ADDRESS,
        chainId: getDefaultChain().id,
        token: 'USDC',
      }),
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new PaymasterUnavailableError(
        `[paymaster] /sponsor returned ${res.status}: ${text}`
      )
    }
    sponsor = (await res.json()) as SponsorResponse
  } catch (err) {
    if (err instanceof PaymasterError) throw err
    throw new PaymasterUnavailableError(
      '[paymaster] /sponsor request failed',
      err
    )
  }

  // 2) sponsored fields を userOp にマージ (v0.7 形式優先)
  const sponsored: UserOperation = {
    ...userOp,
    paymaster: sponsor.paymaster ?? userOp.paymaster,
    paymasterData: sponsor.paymasterData ?? userOp.paymasterData,
    paymasterVerificationGasLimit:
      toBigIntOrUndef(sponsor.paymasterVerificationGasLimit) ??
      userOp.paymasterVerificationGasLimit,
    paymasterPostOpGasLimit:
      toBigIntOrUndef(sponsor.paymasterPostOpGasLimit) ??
      userOp.paymasterPostOpGasLimit,
    callGasLimit:
      toBigIntOrUndef(sponsor.callGasLimit) ?? userOp.callGasLimit,
    verificationGasLimit:
      toBigIntOrUndef(sponsor.verificationGasLimit) ??
      userOp.verificationGasLimit,
    preVerificationGas:
      toBigIntOrUndef(sponsor.preVerificationGas) ?? userOp.preVerificationGas,
    maxFeePerGas:
      toBigIntOrUndef(sponsor.maxFeePerGas) ?? userOp.maxFeePerGas,
    maxPriorityFeePerGas:
      toBigIntOrUndef(sponsor.maxPriorityFeePerGas) ??
      userOp.maxPriorityFeePerGas,
  }

  // 3) bundler / wallet 経由で送信
  if (!walletClient.sendUserOperation) {
    throw new PaymasterError(
      '[paymaster] walletClient.sendUserOperation is not available — Privy AA / viem account-abstraction を初期化してください'
    )
  }

  try {
    return await walletClient.sendUserOperation(sponsored)
  } catch (err) {
    throw new PaymasterError(
      '[paymaster] sendUserOperation failed at bundler',
      err
    )
  }
}
