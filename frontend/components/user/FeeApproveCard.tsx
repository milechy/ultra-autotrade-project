'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/user/FeeApproveCard.tsx
//
// F-S6 non-custodial: ユーザーが operator に aToken を上限付き approve する UX
//   approve 額 = recommended_allowance_usdc (バックエンドが返す上限値, MaxUint256 禁止)
//   署名: Privy 経由でブラウザ署名 (サーバーはユーザー秘密鍵を不所持)
//
// 使用先:
//   - app/(user)/fee-approve/page.tsx  (PWA)
//   - app/(liff)/liff-fee-approve/page.tsx (LIFF)

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { useWallets } from '@privy-io/react-auth'
import { ethers } from 'ethers'
import { CheckCircle2, AlertTriangle, ExternalLink, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { apiFetch } from '@/lib/api/client'

// ---------------------------------------------------------------------------
// ABI 最小定義
// ---------------------------------------------------------------------------

const DATA_PROVIDER_ABI = [
  {
    name: 'getReserveTokensAddresses',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: 'asset', type: 'address' }],
    outputs: [
      { name: 'aTokenAddress', type: 'address' },
      { name: 'stableDebtTokenAddress', type: 'address' },
      { name: 'variableDebtTokenAddress', type: 'address' },
    ],
  },
]

const ERC20_ABI = [
  {
    name: 'allowance',
    type: 'function',
    stateMutability: 'view',
    inputs: [
      { name: 'owner', type: 'address' },
      { name: 'spender', type: 'address' },
    ],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'approve',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [
      { name: 'spender', type: 'address' },
      { name: 'amount', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    name: 'decimals',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint8' }],
  },
]

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

interface AllowanceInfo {
  operator_address: string
  usdc_address: string
  data_provider_address: string
  chain_id: number
  recommended_allowance_usdc: string
  configured: boolean
}

type ApproveState =
  | 'idle'
  | 'checking'
  | 'already_approved'
  | 'needs_approve'
  | 'approving'
  | 'approved'
  | 'error'

// ethers v6 Contract is dynamically typed; use a consistent cast helper
type AnyContract = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [method: string]: (...args: any[]) => Promise<any>
}

function asContract(c: ethers.Contract): AnyContract {
  return c as unknown as AnyContract
}

// ---------------------------------------------------------------------------
// ヘルパー
// ---------------------------------------------------------------------------

function basescanUrl(chainId: number, txHash: string): string {
  const base = chainId === 84532 ? 'https://sepolia.basescan.org' : 'https://basescan.org'
  return `${base}/tx/${txHash}`
}

function truncateAddr(addr: string): string {
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`
}

// ---------------------------------------------------------------------------
// コンポーネント
// ---------------------------------------------------------------------------

interface FeeApproveCardProps {
  /** 承認完了後に呼ばれるコールバック */
  onApproved?: (txHash: string) => void
}

export function FeeApproveCard({ onApproved }: FeeApproveCardProps) {
  const t = useTranslations('UserFeeApproveCard')
  const { wallets } = useWallets()
  const wallet = wallets[0] ?? null

  const [info, setInfo] = useState<AllowanceInfo | null>(null)
  const [aTokenAddress, setATokenAddress] = useState<string | null>(null)
  const [currentAllowanceFmt, setCurrentAllowanceFmt] = useState<string | null>(null)
  const [state, setState] = useState<ApproveState>('idle')
  const [txHash, setTxHash] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [infoLoading, setInfoLoading] = useState(true)

  // バックエンドから allowance-info を取得
  useEffect(() => {
    setInfoLoading(true)
    apiFetch<AllowanceInfo>('/api/v1/fees/allowance-info')
      .then((data) => setInfo(data))
      .catch((err: unknown) => {
        setErrorMsg(err instanceof Error ? err.message : t('errorBackend'))
        setState('error')
      })
      .finally(() => setInfoLoading(false))
  }, [])

  // ウォレット接続 + info 取得後に allowance チェック
  useEffect(() => {
    if (!info || !wallet || !info.configured) return
    if (!info.data_provider_address || !info.usdc_address) return

    setState('checking')

    ;(async () => {
      try {
        const eip1193 = await wallet.getEthereumProvider()
        const provider = new ethers.BrowserProvider(eip1193 as unknown as ethers.Eip1193Provider)

        // aToken アドレスを data provider から取得
        const dp = asContract(new ethers.Contract(info.data_provider_address, DATA_PROVIDER_ABI, provider))
        const [aTokenAddr] = (await dp.getReserveTokensAddresses(info.usdc_address)) as string[]
        setATokenAddress(aTokenAddr)

        // 現在の allowance を確認 — 推奨額と比較
        const aToken = asContract(new ethers.Contract(aTokenAddr, ERC20_ABI, provider))
        const decimals = Number(await aToken.decimals()) as number
        const recommended = ethers.parseUnits(info.recommended_allowance_usdc, decimals)
        const current = BigInt(String(await aToken.allowance(wallet.address, info.operator_address)))
        setCurrentAllowanceFmt((Number(current) / 10 ** decimals).toFixed(2))

        setState(current >= recommended ? 'already_approved' : 'needs_approve')
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : t('errorAllowanceCheck'))
        setState('error')
      }
    })()
  }, [info, wallet])

  async function handleApprove() {
    if (!wallet || !info || !aTokenAddress) return

    setState('approving')
    setErrorMsg(null)
    try {
      const eip1193 = await wallet.getEthereumProvider()
      const provider = new ethers.BrowserProvider(eip1193 as unknown as ethers.Eip1193Provider)
      const signer = await provider.getSigner()

      const aToken = asContract(new ethers.Contract(aTokenAddress, ERC20_ABI, signer))
      const decimals = Number(await aToken.decimals()) as number

      // 上限付き approve — MaxUint256 禁止 (non-custodial §14a)
      const amount = ethers.parseUnits(info.recommended_allowance_usdc, decimals)
      const tx = (await aToken.approve(info.operator_address, amount)) as {
        hash: string
        wait: () => Promise<void>
      }
      setTxHash(tx.hash)
      await tx.wait()

      setState('approved')
      onApproved?.(tx.hash)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('errorApprove')
      // ユーザーキャンセルは error ではなく通知のみ
      if (msg.includes('rejected') || msg.includes('denied') || msg.includes('cancel')) {
        setState('needs_approve')
        setErrorMsg(t('errorSignatureCancelled'))
      } else {
        setErrorMsg(msg)
        setState('error')
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (infoLoading) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardContent className="pt-6 pb-6 flex items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
          <span className="text-sm text-zinc-400">{t('loadingInfo')}</span>
        </CardContent>
      </Card>
    )
  }

  if (!info) {
    return (
      <Card className="border-red-900 bg-zinc-900/60">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-sm text-red-300">{errorMsg ?? t('fetchError')}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!info.configured) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardContent className="pt-4 pb-4">
          <p className="text-sm text-zinc-400">{t('notConfigured')}</p>
        </CardContent>
      </Card>
    )
  }

  if (!wallet) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-400 shrink-0 mt-0.5" />
            <p className="text-sm text-yellow-300">{t('connectWallet')}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-zinc-800 bg-zinc-900/60">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{t('cardTitle')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 承認情報 */}
        <div className="space-y-2 text-sm">
          <InfoRow
            label={t('labelOperator')}
            value={truncateAddr(info.operator_address)}
          />
          <InfoRow
            label={t('labelAmount')}
            value={`${Number(info.recommended_allowance_usdc).toFixed(2)} USDC`}
          />
          {aTokenAddress && (
            <InfoRow
              label={t('labelAToken')}
              value={truncateAddr(aTokenAddress)}
            />
          )}
          <InfoRow
            label={t('labelNetwork')}
            value={info.chain_id === 84532 ? t('networkTestnet') : t('networkMainnet')}
          />
          {currentAllowanceFmt !== null && (
            <InfoRow
              label={t('labelCurrentAllowance')}
              value={`${currentAllowanceFmt} USDC`}
            />
          )}
        </div>

        {/* 注意書き */}
        <p className="text-xs text-zinc-500 leading-relaxed">
          {t('noticeText')}
        </p>

        {/* 状態別 UI */}
        {state === 'checking' && (
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
            <span className="text-sm text-zinc-400">{t('checkingStatus')}</span>
          </div>
        )}

        {state === 'already_approved' && (
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
            <span className="text-sm text-emerald-400 font-medium">{t('alreadyApproved')}</span>
          </div>
        )}

        {(state === 'needs_approve' || state === 'idle') && (
          <Button
            className="w-full bg-blue-600 hover:bg-blue-500 text-white"
            onClick={handleApprove}
          >
            {t('approveButton')}
          </Button>
        )}

        {state === 'approving' && (
          <Button className="w-full" disabled>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t('waitingSignature')}
          </Button>
        )}

        {state === 'approved' && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
              <span className="text-sm text-emerald-400 font-medium">{t('approvedLabel')}</span>
            </div>
            {txHash && (
              <a
                href={basescanUrl(info.chain_id, txHash)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-blue-400 hover:underline"
              >
                <ExternalLink className="h-3 w-3" />
                {t('viewOnBasescan')}
              </a>
            )}
          </div>
        )}

        {errorMsg && state !== 'approving' && (
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-xs text-red-300">{errorMsg}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-zinc-400">{label}</span>
      <span className="font-mono text-zinc-200 text-xs">{value}</span>
    </div>
  )
}
