'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// P4: 出金 UI (ノンカストディアル・本人署名のみ)
//
// 重要:
// - 本ページの出金は **常にユーザー本人の Privy 鍵で署名される**。
// - delegated signing (P3) は出金には適用されない (resource exclusion)。
// - backend は tx_hash 記録のみで、送金には一切関与しない。

export const dynamic = 'force-dynamic'

import { useState, useMemo, useEffect, useCallback } from 'react'
import { usePrivy, useWallets } from '@privy-io/react-auth'
import {
  encodeFunctionData,
  parseUnits,
  formatUnits,
  isAddress,
  createPublicClient,
  http as viemHttp,
  type PublicClient,
} from 'viem'
import { base } from 'viem/chains'
import { AlertTriangle, ShieldCheck, ExternalLink, Loader2, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import AuthGuard from '@/components/AuthGuard'
import { postJson } from '@/lib/api/http'

// USDC on Base mainnet
const USDC_BASE_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913' as const
const USDC_DECIMALS = 6
const DEFAULT_CHAIN_ID = parseInt(process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453', 10)
const BASE_RPC_URL = process.env.NEXT_PUBLIC_BASE_RPC_URL || 'https://mainnet.base.org'
// ETH price (USD) fallback; gas 表示の概算用。実値は estimateContractGas の結果に乗じる。
const ETH_USD_FALLBACK = parseFloat(process.env.NEXT_PUBLIC_ETH_USD_FALLBACK || '3500')

// transfer(address,uint256) + balanceOf(address) ABI (minimal)
const USDC_ABI = [
  {
    type: 'function',
    name: 'transfer',
    stateMutability: 'nonpayable',
    inputs: [
      { name: 'to', type: 'address' },
      { name: 'amount', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    type: 'function',
    name: 'balanceOf',
    stateMutability: 'view',
    inputs: [{ name: 'account', type: 'address' }],
    outputs: [{ name: '', type: 'uint256' }],
  },
] as const

// エラー型分類: ウォレット/RPC から返ってくる例外をユーザーフレンドリーに分岐表示する。
type WithdrawErrorKind =
  | 'user_rejected'
  | 'insufficient_funds'
  | 'wrong_network'
  | 'rpc_error'
  | 'address_invalid'
  | 'amount_invalid'
  | 'unknown'

type WithdrawError = {
  kind: WithdrawErrorKind
  message: string
  raw?: string
}

type TxState =
  | { kind: 'idle' }
  | { kind: 'confirming' }
  | { kind: 'signing' }
  | { kind: 'waiting_receipt'; txHash: string; blockNumber?: bigint }
  | { kind: 'logging'; txHash: string }
  | { kind: 'done'; txHash: string; blockNumber?: bigint }
  | { kind: 'error'; error: WithdrawError }

function shortHash(hash: string): string {
  if (hash.length <= 12) return hash
  return `${hash.slice(0, 8)}…${hash.slice(-6)}`
}

/**
 * ウォレット/RPC エラーをユーザー向けカテゴリに分類する。
 * EIP-1193 のエラーコードと message 文字列の両方をチェック。
 */
function classifyError(err: unknown): WithdrawError {
  const raw =
    err instanceof Error
      ? err.message
      : typeof err === 'string'
        ? err
        : JSON.stringify(err ?? 'unknown error')
  const lower = raw.toLowerCase()
  // EIP-1193 error code (4001 = user rejected)
  const code =
    err && typeof err === 'object' && 'code' in err
      ? (err as { code?: number | string }).code
      : undefined
  if (code === 4001 || lower.includes('user rejected') || lower.includes('user denied')) {
    return { kind: 'user_rejected', message: '署名がキャンセルされました。', raw }
  }
  if (lower.includes('insufficient funds') || lower.includes('insufficient balance') || lower.includes('exceeds balance')) {
    return {
      kind: 'insufficient_funds',
      message: '残高またはガス代が不足しています。USDC 残高と ETH (gas) を確認してください。',
      raw,
    }
  }
  if (lower.includes('wrong network') || lower.includes('chain mismatch') || lower.includes('unsupported chain') || lower.includes('switch chain')) {
    return {
      kind: 'wrong_network',
      message: `Base ネットワーク (chainId=${DEFAULT_CHAIN_ID}) に切り替えてください。`,
      raw,
    }
  }
  if (
    lower.includes('rpc') ||
    lower.includes('network error') ||
    lower.includes('timeout') ||
    lower.includes('fetch failed') ||
    lower.includes('http request failed')
  ) {
    return {
      kind: 'rpc_error',
      message: 'RPC との通信に失敗しました。時間を置いて再試行してください。',
      raw,
    }
  }
  return { kind: 'unknown', message: `送信に失敗しました: ${raw}`, raw }
}

/**
 * user_actions ロギング (best-effort)。
 * バックエンドの user_actions エンドポイントが未配線でも UI 進行を止めない。
 */
async function logUserAction(actionType: string, payload: Record<string, unknown>): Promise<void> {
  try {
    await postJson('/api/users/actions', { action_type: actionType, payload })
  } catch (err) {
    // 失敗は致命的でない。console のみ。
    console.warn(`[withdraw] logUserAction(${actionType}) failed:`, err)
  }
}

function NonCustodialNotice() {
  return (
    <Alert className="border-blue-800 bg-blue-950/40">
      <ShieldCheck className="h-4 w-4 text-blue-400" />
      <AlertDescription className="text-blue-200 text-xs leading-relaxed">
        <strong className="font-semibold">ノンカストディアル出金:</strong>{' '}
        本サービスはノンカストディアルです。出金は常にあなた自身の Privy 鍵による署名が必要です。
        delegated signing (代理署名) は出金には<strong>適用されません</strong>。
        運営はあなたの資金を移動する権限を持ちません。
      </AlertDescription>
    </Alert>
  )
}

function ConfirmDialog({
  toAddress,
  amount,
  gasEstimateText,
  onConfirm,
  onCancel,
  isLoading,
}: {
  toAddress: string
  amount: string
  gasEstimateText: string | null
  onConfirm: () => void
  onCancel: () => void
  isLoading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-sm rounded-xl bg-zinc-900 border border-zinc-800 p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-zinc-100">出金内容を確認</h2>
        <div className="mb-4 space-y-3 text-sm">
          <div>
            <div className="text-xs text-zinc-500 mb-1">宛先アドレス</div>
            <div className="font-mono text-zinc-200 break-all text-xs bg-zinc-950 p-2 rounded">
              {toAddress}
            </div>
          </div>
          <div>
            <div className="text-xs text-zinc-500 mb-1">数量</div>
            <div className="font-mono text-zinc-100 text-lg">
              {amount} <span className="text-sm text-zinc-400">USDC</span>
            </div>
          </div>
          <div>
            <div className="text-xs text-zinc-500 mb-1">ネットワーク</div>
            <div className="text-zinc-200">Base (Chain {DEFAULT_CHAIN_ID})</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500 mb-1">推定 gas 代</div>
            <div className="font-mono text-zinc-200 text-sm">
              {gasEstimateText ?? '見積もり中...'}
            </div>
          </div>
        </div>

        <Alert className="mb-4 border-yellow-800 bg-yellow-950/40">
          <AlertTriangle className="h-4 w-4 text-yellow-400" />
          <AlertDescription className="text-yellow-200 text-xs">
            この操作にはあなたの Privy 鍵による<strong className="font-semibold">本人署名</strong>が必要です。
            送金後の取り消しはできません。
          </AlertDescription>
        </Alert>

        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={onCancel} disabled={isLoading}>
            キャンセル
          </Button>
          <Button
            className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50"
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                処理中...
              </>
            ) : (
              '署名して送金'
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

function WithdrawPageInner() {
  const { authenticated } = usePrivy()
  const { wallets } = useWallets()
  const wallet = wallets[0] ?? null
  const fromAddress = wallet?.address ?? null

  const [toAddress, setToAddress] = useState('')
  const [amount, setAmount] = useState('')
  const [txState, setTxState] = useState<TxState>({ kind: 'idle' })
  const [showConfirm, setShowConfirm] = useState(false)

  // 残高 & gas 見積もり state
  const [usdcBalance, setUsdcBalance] = useState<bigint | null>(null)
  const [gasEstimateText, setGasEstimateText] = useState<string | null>(null)

  // viem public client (read-only RPC)
  const publicClient = useMemo<PublicClient>(() => {
    return createPublicClient({
      chain: base,
      transport: viemHttp(BASE_RPC_URL),
    }) as PublicClient
  }, [])

  // 入力バリデーション (viem isAddress による bech32/checksum 含む)
  const addressValid = useMemo(() => {
    if (!toAddress) return false
    return isAddress(toAddress)
  }, [toAddress])

  const amountNum = useMemo(() => {
    if (!amount) return null
    const n = parseFloat(amount)
    if (isNaN(n) || n <= 0) return null
    const parts = amount.split('.')
    if (parts.length === 2 && parts[1].length > USDC_DECIMALS) return null
    return n
  }, [amount])

  const amountUnits = useMemo(() => {
    if (amountNum == null) return null
    try {
      return parseUnits(amount, USDC_DECIMALS)
    } catch {
      return null
    }
  }, [amount, amountNum])

  // 残高超過チェック
  const amountExceedsBalance = useMemo(() => {
    if (amountUnits == null || usdcBalance == null) return false
    return amountUnits > usdcBalance
  }, [amountUnits, usdcBalance])

  const amountValid = amountNum != null && !amountExceedsBalance
  const canSubmit = authenticated && wallet != null && addressValid && amountValid

  // USDC 残高取得
  useEffect(() => {
    let cancelled = false
    if (!fromAddress) {
      setUsdcBalance(null)
      return
    }
    ;(async () => {
      try {
        const bal = (await publicClient.readContract({
          address: USDC_BASE_ADDRESS,
          abi: USDC_ABI,
          functionName: 'balanceOf',
          args: [fromAddress as `0x${string}`],
        })) as bigint
        if (!cancelled) setUsdcBalance(bal)
      } catch (err) {
        console.warn('[withdraw] balanceOf failed:', err)
        if (!cancelled) setUsdcBalance(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [fromAddress, publicClient])

  // gas 見積もり (確認ダイアログを開く前に再計算)
  const estimateGas = useCallback(async (): Promise<string | null> => {
    if (!fromAddress || amountUnits == null || !addressValid) return null
    try {
      const gasUnits = await publicClient.estimateContractGas({
        address: USDC_BASE_ADDRESS,
        abi: USDC_ABI,
        functionName: 'transfer',
        args: [toAddress as `0x${string}`, amountUnits],
        account: fromAddress as `0x${string}`,
      })
      const gasPrice = await publicClient.getGasPrice()
      const weiCost = gasUnits * gasPrice
      const ethCost = parseFloat(formatUnits(weiCost, 18))
      const usdCost = ethCost * ETH_USD_FALLBACK
      return `${ethCost.toFixed(6)} ETH (約 $${usdCost.toFixed(3)})`
    } catch (err) {
      console.warn('[withdraw] gas estimate failed:', err)
      return null
    }
  }, [fromAddress, amountUnits, addressValid, toAddress, publicClient])

  const handleOpenConfirm = async () => {
    if (!canSubmit) return
    setTxState({ kind: 'idle' })
    setGasEstimateText(null)
    setShowConfirm(true)
    // 非同期で gas 見積もり
    const est = await estimateGas()
    setGasEstimateText(est ?? '見積もり失敗 (RPC エラー)')
  }

  const handleConfirm = async () => {
    if (!wallet || !fromAddress || !addressValid || amountUnits == null) return

    setTxState({ kind: 'signing' })

    // chain id 事前チェック
    try {
      const provider = await wallet.getEthereumProvider()
      const chainIdHex = (await provider.request({ method: 'eth_chainId' })) as string
      const currentChainId = parseInt(chainIdHex, 16)
      if (currentChainId !== DEFAULT_CHAIN_ID) {
        setTxState({
          kind: 'error',
          error: {
            kind: 'wrong_network',
            message: `Base ネットワーク (chainId=${DEFAULT_CHAIN_ID}) に切り替えてください。現在: ${currentChainId}`,
          },
        })
        return
      }
    } catch (err) {
      // chain_id 取得失敗時は致命的でないので進める (送信時に弾かれる)
      console.warn('[withdraw] eth_chainId check failed:', err)
    }

    // user_actions: withdrawal_initiated (送信前)
    await logUserAction('withdrawal_initiated', {
      to_address: toAddress,
      amount_usdc: amount,
      network: 'base',
      chain_id: DEFAULT_CHAIN_ID,
    })

    let txHash: string
    try {
      // viem encodeFunctionData で transfer(to, amount) を組み立て
      const data = encodeFunctionData({
        abi: USDC_ABI,
        functionName: 'transfer',
        args: [toAddress as `0x${string}`, amountUnits],
      })

      const provider = await wallet.getEthereumProvider()
      txHash = (await provider.request({
        method: 'eth_sendTransaction',
        params: [
          {
            from: fromAddress,
            to: USDC_BASE_ADDRESS,
            data,
            value: '0x0',
          },
        ],
      })) as string
    } catch (err) {
      const classified = classifyError(err)
      setTxState({ kind: 'error', error: classified })
      await logUserAction('withdrawal_failed', {
        to_address: toAddress,
        amount_usdc: amount,
        error_kind: classified.kind,
        error_message: classified.message,
      })
      return
    }

    // receipt 待機
    setTxState({ kind: 'waiting_receipt', txHash })
    let blockNumber: bigint | undefined
    try {
      const receipt = await publicClient.waitForTransactionReceipt({
        hash: txHash as `0x${string}`,
        timeout: 120_000,
        pollingInterval: 2_000,
      })
      blockNumber = receipt.blockNumber
      setTxState({ kind: 'waiting_receipt', txHash, blockNumber })
      if (receipt.status !== 'success') {
        const errMsg = 'トランザクションは取り込まれましたが失敗しました (revert)。'
        setTxState({
          kind: 'error',
          error: { kind: 'unknown', message: errMsg, raw: errMsg },
        })
        await logUserAction('withdrawal_failed', {
          tx_hash: txHash,
          block_number: blockNumber?.toString(),
          error_kind: 'revert',
          error_message: errMsg,
        })
        return
      }
    } catch (err) {
      const classified = classifyError(err)
      // receipt 待機失敗は致命的だが tx 自体は発火済みのため、エラー表示は緩める
      setTxState({
        kind: 'error',
        error: {
          ...classified,
          message: `tx は送信済みですが receipt 取得に失敗: ${classified.message} (tx=${shortHash(txHash)})`,
        },
      })
      await logUserAction('withdrawal_failed', {
        tx_hash: txHash,
        error_kind: classified.kind,
        error_message: classified.message,
      })
      return
    }

    // バックエンドにログ記録 (idempotent)
    setTxState({ kind: 'logging', txHash })
    try {
      await postJson('/api/users/withdrawals', {
        tx_hash: txHash,
        to_address: toAddress,
        amount_usdc: amount,
        network: 'base',
      })
    } catch (logErr) {
      // ログ失敗は致命的でない: tx は既に confirm 済み
      console.warn('Failed to log withdrawal to backend:', logErr)
    }

    // user_actions: withdrawal_completed (receipt 後)
    await logUserAction('withdrawal_completed', {
      tx_hash: txHash,
      block_number: blockNumber?.toString(),
      to_address: toAddress,
      amount_usdc: amount,
      network: 'base',
    })

    setTxState({ kind: 'done', txHash, blockNumber })
    setShowConfirm(false)
    // 入力リセット
    setToAddress('')
    setAmount('')
    // 残高再取得
    try {
      const bal = (await publicClient.readContract({
        address: USDC_BASE_ADDRESS,
        abi: USDC_ABI,
        functionName: 'balanceOf',
        args: [fromAddress as `0x${string}`],
      })) as bigint
      setUsdcBalance(bal)
    } catch {
      /* noop */
    }
  }

  const handleCancel = () => {
    setShowConfirm(false)
    setTxState({ kind: 'idle' })
  }

  const balanceText =
    usdcBalance != null
      ? `${parseFloat(formatUnits(usdcBalance, USDC_DECIMALS)).toFixed(6)} USDC`
      : '取得中...'

  const isProcessing =
    txState.kind === 'signing' ||
    txState.kind === 'waiting_receipt' ||
    txState.kind === 'logging'

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-xl mx-auto px-4 py-8 space-y-4">
        <div>
          <h1 className="text-2xl font-bold mb-2">USDC 出金</h1>
          <p className="text-sm text-zinc-400">Base ネットワーク上の USDC を指定アドレスへ送金します。</p>
        </div>

        <NonCustodialNotice />

        {!authenticated && (
          <Alert className="border-red-800 bg-red-950/40">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            <AlertDescription className="text-red-200 text-sm">
              ウォレット未接続です。先にウォレットを接続してください。
            </AlertDescription>
          </Alert>
        )}

        <Card className="border-zinc-800 bg-zinc-900/60">
          <CardHeader>
            <CardTitle className="text-base text-zinc-200">出金情報</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {fromAddress && (
              <div>
                <label className="text-xs text-zinc-500 uppercase tracking-wide block mb-1">
                  送金元 (あなた)
                </label>
                <div className="font-mono text-xs text-zinc-300 bg-zinc-950 p-2 rounded break-all">
                  {fromAddress}
                </div>
                <div className="mt-1 text-xs text-zinc-400">
                  残高: <span className="font-mono text-zinc-200">{balanceText}</span>
                </div>
              </div>
            )}

            <div>
              <label htmlFor="to-address" className="text-xs text-zinc-500 uppercase tracking-wide block mb-1">
                宛先アドレス
              </label>
              <input
                id="to-address"
                type="text"
                placeholder="0x..."
                value={toAddress}
                onChange={(e) => setToAddress(e.target.value.trim())}
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm font-mono text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-blue-600"
                disabled={!authenticated || isProcessing}
              />
              {toAddress && !addressValid && (
                <p className="mt-1 text-xs text-red-400">アドレス形式が不正です (EIP-55 checksum / 42 文字)</p>
              )}
            </div>

            <div>
              <label htmlFor="amount" className="text-xs text-zinc-500 uppercase tracking-wide block mb-1">
                数量 (USDC)
              </label>
              <input
                id="amount"
                type="text"
                inputMode="decimal"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value.trim())}
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-lg font-mono text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-blue-600"
                disabled={!authenticated || isProcessing}
              />
              {amount && amountNum == null && (
                <p className="mt-1 text-xs text-red-400">
                  正の数値で入力してください (小数点以下最大 {USDC_DECIMALS} 桁)
                </p>
              )}
              {amount && amountNum != null && amountExceedsBalance && (
                <p className="mt-1 text-xs text-red-400">
                  USDC 残高 ({balanceText}) を超えています。
                </p>
              )}
              <p className="mt-1 text-xs text-zinc-500">
                ETH (gas) 残高は送信時にウォレット側で検証されます。
              </p>
            </div>

            {txState.kind === 'waiting_receipt' && (
              <Alert className="border-blue-800 bg-blue-950/40">
                <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />
                <AlertDescription className="text-blue-200 text-sm">
                  <div className="mb-1">
                    待機中...{' '}
                    {txState.blockNumber != null && (
                      <span className="font-mono text-xs">(block {txState.blockNumber.toString()})</span>
                    )}
                  </div>
                  <a
                    href={`https://basescan.org/tx/${txState.txHash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-300 hover:underline font-mono text-xs"
                  >
                    {shortHash(txState.txHash)}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </AlertDescription>
              </Alert>
            )}

            {txState.kind === 'logging' && (
              <Alert className="border-blue-800 bg-blue-950/40">
                <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />
                <AlertDescription className="text-blue-200 text-sm">
                  記録中...
                </AlertDescription>
              </Alert>
            )}

            {txState.kind === 'done' && (
              <Alert className="border-emerald-800 bg-emerald-950/40">
                <CheckCircle className="h-4 w-4 text-emerald-400" />
                <AlertDescription className="text-emerald-200 text-sm">
                  <div className="mb-1">
                    出金 tx が確定しました。
                    {txState.blockNumber != null && (
                      <span className="ml-1 font-mono text-xs">
                        (block {txState.blockNumber.toString()})
                      </span>
                    )}
                  </div>
                  <a
                    href={`https://basescan.org/tx/${txState.txHash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-300 hover:underline font-mono text-xs"
                  >
                    Basescan で開く: {shortHash(txState.txHash)}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </AlertDescription>
              </Alert>
            )}

            {txState.kind === 'error' && (
              <Alert className="border-red-800 bg-red-950/40">
                <AlertTriangle className="h-4 w-4 text-red-400" />
                <AlertDescription className="text-red-200 text-sm">
                  <div className="font-semibold mb-1">
                    {(() => {
                      switch (txState.error.kind) {
                        case 'user_rejected':
                          return 'ユーザーがキャンセル'
                        case 'insufficient_funds':
                          return '残高不足'
                        case 'wrong_network':
                          return 'ネットワーク違い'
                        case 'rpc_error':
                          return 'RPC エラー'
                        case 'address_invalid':
                          return 'アドレス不正'
                        case 'amount_invalid':
                          return '数量不正'
                        default:
                          return 'エラー'
                      }
                    })()}
                  </div>
                  <div>{txState.error.message}</div>
                </AlertDescription>
              </Alert>
            )}

            <Button
              size="lg"
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!canSubmit || isProcessing}
              onClick={handleOpenConfirm}
            >
              出金内容を確認
            </Button>
          </CardContent>
        </Card>
      </div>

      {showConfirm && (
        <ConfirmDialog
          toAddress={toAddress}
          amount={amount}
          gasEstimateText={gasEstimateText}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          isLoading={isProcessing}
        />
      )}
    </div>
  )
}

export default function WithdrawPage() {
  return (
    <AuthGuard>
      <WithdrawPageInner />
    </AuthGuard>
  )
}
