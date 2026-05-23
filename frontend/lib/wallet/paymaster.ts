// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// ERC-20 Paymaster client helper (Base).
//
// 仕様原文では Paymaster は将来扱いだったが、Q3 reframe で MVP 格上げ。
// ユーザの初回 tx 前にガス額(USDC)を見積もり、承認 UI を経由して
// Paymaster API へ UserOperation を投げる導線をここに集約する。
//
// TODO(privy): Privy の useSendTransaction() / EIP-4337 bundler 接続を結合する。
// TODO(viem):  viem の TransactionRequest -> UserOperation 変換を実装する。
// TODO(estim): 実 Paymaster (e.g. Pimlico / Alchemy Account Kit) の見積 RPC を結ぶ。

export type TxHash = `0x${string}`

export interface PaymasterConfig {
  url: string
  apiKey: string
}

export interface TransactionRequest {
  to: `0x${string}`
  data?: `0x${string}`
  value?: bigint
}

export interface UserOperation {
  sender: `0x${string}`
  nonce: bigint
  callData: `0x${string}`
  // 実装時に EIP-4337 の他フィールド (callGasLimit, verificationGasLimit, ...) を追加
}

// 最小の WalletClient interface (Privy / wagmi / viem いずれにも適応できるよう緩く)
export interface PaymasterWalletClient {
  account?: { address: `0x${string}` }
  sendTransaction?: (tx: TransactionRequest) => Promise<TxHash>
}

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
 * tx のガス代を USDC 建てで見積もる雛形。
 * 実装時は Paymaster の `pm_estimateUserOperationGas` 相当を叩き、
 * 返ってきた gasLimit * gasPrice を USDC レートで換算する。
 *
 * 現状は安全側 (UI に表示するためのプレースホルダ値) を返す。
 */
export async function estimateGasInUsdc(
  _tx: TransactionRequest
): Promise<bigint> {
  // TODO(estim): 実 RPC 呼び出し。現状は 0.10 USDC (6 decimals) を仮置き。
  const PLACEHOLDER_USDC_6DP = 100_000n // = 0.10 USDC
  return PLACEHOLDER_USDC_6DP
}

/**
 * USDC (6 decimals, bigint) を画面表示用の数値に変換するヘルパ。
 */
export function formatUsdc6dp(amount: bigint): number {
  // bigint -> number で精度は落ちるが UI 表示用なので許容。
  return Number(amount) / 1_000_000
}

/**
 * UserOperation を Paymaster 経由で送信する雛形。
 * 実装は Privy embedded wallet の signUserOperation() + Bundler RPC への
 * eth_sendUserOperation を組み合わせる予定。
 *
 * TODO(privy): Privy の useSendTransaction との接続点をここに追加。
 */
export async function sendUserOpWithPaymaster(
  _walletClient: PaymasterWalletClient,
  _userOp: UserOperation
): Promise<TxHash> {
  const { url, apiKey } = getPaymasterConfig()
  if (!url || !apiKey) {
    throw new Error(
      '[paymaster] NEXT_PUBLIC_PAYMASTER_URL / NEXT_PUBLIC_PAYMASTER_API_KEY が未設定です'
    )
  }
  // TODO(impl): fetch(url, { headers: { 'x-api-key': apiKey }, ... }) で
  //             eth_sendUserOperation を投げ、txHash を返す。
  throw new Error('[paymaster] sendUserOpWithPaymaster: not implemented yet')
}
