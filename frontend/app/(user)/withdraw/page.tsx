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

import { useState, useMemo } from 'react'
import { usePrivy, useWallets } from '@privy-io/react-auth'
import { encodeFunctionData, parseUnits, isAddress } from 'viem'
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

// transfer(address,uint256) ABI (minimal)
const USDC_TRANSFER_ABI = [
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
] as const

type TxState =
  | { kind: 'idle' }
  | { kind: 'confirming' }
  | { kind: 'signing' }
  | { kind: 'logging'; txHash: string }
  | { kind: 'done'; txHash: string }
  | { kind: 'error'; message: string }

function shortHash(hash: string): string {
  if (hash.length <= 12) return hash
  return `${hash.slice(0, 8)}…${hash.slice(-6)}`
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
  onConfirm,
  onCancel,
  isLoading,
}: {
  toAddress: string
  amount: string
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

  // バリデーション
  const addressValid = useMemo(() => {
    if (!toAddress) return false
    return isAddress(toAddress)
  }, [toAddress])

  const amountValid = useMemo(() => {
    if (!amount) return false
    const n = parseFloat(amount)
    if (isNaN(n) || n <= 0) return false
    // 最大 6 桁の小数を許可 (USDC decimals=6)
    const parts = amount.split('.')
    if (parts.length === 2 && parts[1].length > USDC_DECIMALS) return false
    return true
  }, [amount])

  const canSubmit = authenticated && wallet != null && addressValid && amountValid

  const handleOpenConfirm = () => {
    if (!canSubmit) return
    setTxState({ kind: 'idle' })
    setShowConfirm(true)
  }

  const handleConfirm = async () => {
    if (!wallet || !fromAddress || !addressValid || !amountValid) return

    setTxState({ kind: 'signing' })

    try {
      // viem encodeFunctionData で transfer(to, amount) を組み立て
      const amountUnits = parseUnits(amount, USDC_DECIMALS)
      const data = encodeFunctionData({
        abi: USDC_TRANSFER_ABI,
        functionName: 'transfer',
        args: [toAddress as `0x${string}`, amountUnits],
      })

      // Privy ウォレットの EIP-1193 provider で sendTransaction
      const provider = await wallet.getEthereumProvider()
      const txHash = (await provider.request({
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

      // バックエンドにログ記録
      setTxState({ kind: 'logging', txHash })
      try {
        await postJson('/api/users/withdrawals', {
          tx_hash: txHash,
          to_address: toAddress,
          amount_usdc: amount,
          network: 'base',
        })
      } catch (logErr) {
        // ログ失敗は致命的でない: tx は既に発火済み。warn のみ
        console.warn('Failed to log withdrawal to backend:', logErr)
      }

      setTxState({ kind: 'done', txHash })
      setShowConfirm(false)
      // 入力リセット
      setToAddress('')
      setAmount('')
    } catch (err) {
      const message = err instanceof Error ? err.message : '署名または送信に失敗しました'
      setTxState({ kind: 'error', message })
    }
  }

  const handleCancel = () => {
    setShowConfirm(false)
    setTxState({ kind: 'idle' })
  }

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
                disabled={!authenticated}
              />
              {toAddress && !addressValid && (
                <p className="mt-1 text-xs text-red-400">アドレス形式が不正です (0x で始まる 42 文字)</p>
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
                disabled={!authenticated}
              />
              {amount && !amountValid && (
                <p className="mt-1 text-xs text-red-400">
                  正の数値で入力してください (小数点以下最大 {USDC_DECIMALS} 桁)
                </p>
              )}
              <p className="mt-1 text-xs text-zinc-500">
                残高チェックは送信時にウォレット側で行われます (不足の場合は失敗)
              </p>
            </div>

            {txState.kind === 'done' && (
              <Alert className="border-emerald-800 bg-emerald-950/40">
                <CheckCircle className="h-4 w-4 text-emerald-400" />
                <AlertDescription className="text-emerald-200 text-sm">
                  <div className="mb-1">出金 tx を送信しました。</div>
                  <a
                    href={`https://basescan.org/tx/${txState.txHash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-300 hover:underline font-mono text-xs"
                  >
                    {shortHash(txState.txHash)}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </AlertDescription>
              </Alert>
            )}

            {txState.kind === 'error' && (
              <Alert className="border-red-800 bg-red-950/40">
                <AlertTriangle className="h-4 w-4 text-red-400" />
                <AlertDescription className="text-red-200 text-sm">
                  {txState.message}
                </AlertDescription>
              </Alert>
            )}

            <Button
              size="lg"
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!canSubmit}
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
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          isLoading={txState.kind === 'signing' || txState.kind === 'logging'}
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
