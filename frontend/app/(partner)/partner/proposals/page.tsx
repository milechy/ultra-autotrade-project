'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useCallback, useEffect, useState } from 'react'
import { CheckCircle, XCircle, Loader2, ClipboardList } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useWallets } from '@privy-io/react-auth'
import { useSmartWallets } from '@privy-io/react-auth/smart-wallets'
import { ethers } from 'ethers'
import { getStoredToken } from '@/lib/auth'
import { toUserOpCall } from '@/lib/wallet/userop'
import {
  fetchAdminProposalStats,
  listAdminProposals,
  rejectProposal,
  buildPartnerTx,
  submitPartnerTx,
  type AdminProposal,
  type AdminProposalStats,
} from '@/lib/api/admin-proposals'
import { useTranslations, useLocale } from 'next-intl'

export default function PartnerProposalsPage() {
  const t = useTranslations('PartnerProposals')
  const locale = useLocale()

  const FILTER_OPTIONS = [
    { value: '', label: t('filterAll') },
    { value: 'pending', label: t('status_pending') },
    { value: 'approved', label: t('status_approved') },
    { value: 'rejected', label: t('status_rejected') },
    { value: 'executed', label: t('status_executed') },
  ]

  const [stats, setStats] = useState<AdminProposalStats | null>(null)
  const [proposals, setProposals] = useState<AdminProposal[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [signingStep, setSigningStep] = useState<string | null>(null)

  const token = getStoredToken()
  const { wallets } = useWallets()
  // Smart Wallet (AA) client。設定済 (SCW ユーザー) なら UserOp 経路、未設定なら EOA 経路。
  const { client: scwClient } = useSmartWallets()

  const loadData = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      const [statsData, listData] = await Promise.all([
        fetchAdminProposalStats(token),
        listAdminProposals(token, { status: statusFilter || undefined, page, limit: 20 }),
      ])
      setStats(statsData)
      setProposals(listData.items)
      setTotal(listData.total)
    } catch {
      setError(t('fetchError'))
    } finally {
      setIsLoading(false)
    }
  }, [token, statusFilter, page, t])

  useEffect(() => {
    void loadData()
  }, [loadData])

  /**
   * 方式2: パートナー本人署名 (Privy)
   * 1. build-tx でサーバーから未署名 tx を取得
   * 2. Privy を通じてパートナーが approve → supply/withdraw を順に署名・送信
   * 3. submit-tx で最終 tx_hash をバックエンドに報告
   */
  const handleApprove = async (id: number) => {
    if (!token) return

    setActionLoading(id)
    setSigningStep(null)
    setError(null)

    try {
      // Step 1: 未署名 tx をサーバーから取得
      setSigningStep(t('signingPrepare'))
      const txData = await buildPartnerTx(id, token)

      let finalTxHash: string

      if (scwClient) {
        // ── Smart Wallet (ERC-4337 AA) 経路: ガスは paymaster 肩代わり (ETH 不要)。──
        // approve+supply は 1 UserOp にバッチ。userOpHash → submit-tx (slice3b) が
        // bundler の eth_getUserOperationReceipt で success / sender(=SCW) を検証する。
        let calls: ReturnType<typeof toUserOpCall>[]
        if (txData.operation === 'SUPPLY' && txData.approve_tx && txData.supply_tx) {
          calls = [toUserOpCall(txData.approve_tx), toUserOpCall(txData.supply_tx)]
        } else if (txData.operation === 'WITHDRAW' && txData.withdraw_tx) {
          calls = [toUserOpCall(txData.withdraw_tx)]
        } else {
          throw new Error(t('errUnsupportedOp', { op: txData.operation }))
        }
        setSigningStep(t('signingSupplyStep'))
        finalTxHash = await scwClient.sendUserOperation({ calls })
      } else {
        // ── EOA 経路 (従来・unchanged): embedded wallet (Privy TEE) のみ使用。──
        // 外部 wallet (MetaMask 等) は秘密鍵がサーバーに渡る懸念があるため除外。
        const wallet = wallets.find(w => w.walletClientType === 'privy') ?? null
        if (!wallet) {
          setError(t('noWallet'))
          return
        }
        // EIP-1193 プロバイダー取得 (Privy が署名ポップアップを表示)
        const eip1193 = await wallet.getEthereumProvider()
        const ethProvider = new ethers.BrowserProvider(eip1193 as ethers.Eip1193Provider)

        if (txData.operation === 'SUPPLY' && txData.approve_tx && txData.supply_tx) {
          // SUPPLY: approve → supply の順に署名・送信
          setSigningStep(t('signingApproveStep'))
          const approveTxHash = await eip1193.request({
            method: 'eth_sendTransaction',
            params: [{
              to: txData.approve_tx.to,
              data: txData.approve_tx.data,
              from: txData.approve_tx.from,
              value: '0x0',
            }],
          }) as string

          // approve の確認を待ってから supply を送信
          setSigningStep(t('signingApproveConfirm'))
          const approveReceipt = await ethProvider.waitForTransaction(approveTxHash)
          if (approveReceipt === null || approveReceipt.status === 0) {
            throw new Error(t('errApproveRevert'))
          }

          setSigningStep(t('signingSupplyStep'))
          finalTxHash = await eip1193.request({
            method: 'eth_sendTransaction',
            params: [{
              to: txData.supply_tx.to,
              data: txData.supply_tx.data,
              from: txData.supply_tx.from,
              value: '0x0',
            }],
          }) as string

        } else if (txData.operation === 'WITHDRAW' && txData.withdraw_tx) {
          // WITHDRAW: withdraw を署名・送信
          setSigningStep(t('signingWithdrawStep'))
          finalTxHash = await eip1193.request({
            method: 'eth_sendTransaction',
            params: [{
              to: txData.withdraw_tx.to,
              data: txData.withdraw_tx.data,
              from: txData.withdraw_tx.from,
              value: '0x0',
            }],
          }) as string

        } else {
          throw new Error(t('errUnsupportedOp', { op: txData.operation }))
        }
      }

      // Step 3: tx_hash をバックエンドに報告
      setSigningStep(t('signingRecording'))
      await submitPartnerTx(id, finalTxHash, txData.wallet_address, token)
      await loadData()

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      // ユーザーキャンセルは正常操作
      if (msg.includes('User rejected') || msg.includes('user rejected')) {
        setError(t('errCancelled'))
      } else {
        setError(t('errApprove', { msg }))
      }
    } finally {
      setActionLoading(null)
      setSigningStep(null)
    }
  }

  const handleReject = async (id: number) => {
    if (!token) return
    setActionLoading(id)
    try {
      await rejectProposal(id, token)
      await loadData()
    } catch {
      setError(t('errReject'))
    } finally {
      setActionLoading(null)
    }
  }

  const totalPages = Math.ceil(total / 20)

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center', gap: 10 }}>
        <ClipboardList style={{ width: 24, height: 24, color: '#2563eb' }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>{t('pageTitle')}</h1>
      </div>

      {/* KPI カード */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>{t('kpiPending')}</CardTitle>
            </CardHeader>
            <CardContent>
              <span style={{ fontSize: 28, fontWeight: 700, color: '#d97706' }}>{stats.pending}</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>{t('kpiApprovedToday')}</CardTitle>
            </CardHeader>
            <CardContent>
              <span style={{ fontSize: 28, fontWeight: 700, color: '#16a34a' }}>{stats.today_approved}</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>{t('kpiRejectedToday')}</CardTitle>
            </CardHeader>
            <CardContent>
              <span style={{ fontSize: 28, fontWeight: 700, color: '#dc2626' }}>{stats.today_rejected}</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>{t('kpiExpired')}</CardTitle>
            </CardHeader>
            <CardContent>
              <span style={{ fontSize: 28, fontWeight: 700, color: '#9ca3af' }}>{stats.expired}</span>
            </CardContent>
          </Card>
        </div>
      )}

      {/* フィルター */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => { setStatusFilter(opt.value); setPage(1) }}
            style={{
              padding: '6px 14px',
              borderRadius: 20,
              border: '1px solid',
              borderColor: statusFilter === opt.value ? '#2563eb' : '#374151',
              background: statusFilter === opt.value ? '#2563eb' : 'transparent',
              color: statusFilter === opt.value ? '#fff' : '#d1d5db',
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {signingStep && (
        <div style={{ padding: '10px 16px', background: '#eff6ff', border: '1px solid #93c5fd', borderRadius: 6, color: '#1d4ed8', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Loader2 style={{ width: 16, height: 16, flexShrink: 0 }} className="animate-spin" />
          {signingStep}
        </div>
      )}

      {error && (
        <div style={{ padding: '10px 16px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, color: '#dc2626', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#666' }}>
          <Loader2 style={{ width: 24, height: 24, display: 'inline-block' }} className="animate-spin" />
          <p style={{ marginTop: 8, color: '#9ca3af' }}>{t('loading')}</p>
        </div>
      ) : proposals.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
          {t('noProposals')}
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #374151', background: 'rgba(255,255,255,0.04)' }}>
                <th style={thStyle}>{t('colUser')}</th>
                <th style={thStyle}>{t('colOperation')}</th>
                <th style={thStyle}>{t('colAsset')}</th>
                <th style={thStyle}>{t('colAmountUsd')}</th>
                <th style={thStyle}>{t('colFeeRate')}</th>
                <th style={thStyle}>{t('colFeeAmount')}</th>
                <th style={thStyle}>{t('colReason')}</th>
                <th style={thStyle}>{t('colCreatedAt')}</th>
                <th style={thStyle}>{t('colStatus')}</th>
                <th style={thStyle}>{t('colAction')}</th>
              </tr>
            </thead>
            <tbody>
              {proposals.map((p) => (
                <tr key={p.id} style={{ borderBottom: '1px solid #374151' }}>
                  <td style={tdStyle}>{p.username ?? t('userIdFallback', { id: p.user_id })}</td>
                  {/* dynamic key: op_SUPPLY / op_WITHDRAW / op_BORROW / op_REPAY — fallback to raw value for unknown operations */}
                  <td style={tdStyle}>{t(`op_${p.operation}` as Parameters<typeof t>[0]) ?? p.operation}</td>
                  <td style={tdStyle}>{p.asset}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    ${Number(p.amount_usd).toFixed(2)}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    {p.fee_rate != null ? `${Number(p.fee_rate).toFixed(2)}%` : '—'}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    {p.fee_amount != null ? `$${Number(p.fee_amount).toFixed(2)}` : '—'}
                  </td>
                  <td style={{ ...tdStyle, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {p.reason}
                  </td>
                  <td style={tdStyle}>{new Date(p.created_at).toLocaleString(locale)}</td>
                  <td style={tdStyle}>
                    {/* dynamic key: status_pending / status_approved / status_rejected / status_executed / status_expired */}
                    <span style={statusBadgeStyle(p.status)}>
                      {t(`status_${p.status}` as Parameters<typeof t>[0]) ?? p.status}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                    {p.status === 'pending' && (
                      <div style={{ display: 'flex', gap: 6 }}>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-green-500 text-green-700 hover:bg-green-50" disabled={actionLoading === p.id}>
                              {actionLoading === p.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <><CheckCircle className="h-3 w-3 mr-1" />{t('actionApprove')}</>}
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle className="flex items-center gap-2">
                                <CheckCircle className="h-5 w-5 text-green-600" />
                                {t('confirmApproveTitle')}
                              </AlertDialogTitle>
                              <AlertDialogDescription asChild>
                                <div>
                                  <p>
                                    {t('confirmApproveDesc', {
                                      username: p.username ?? t('userIdFallback', { id: p.user_id }),
                                      operation: t(`op_${p.operation}` as Parameters<typeof t>[0]),
                                      asset: p.asset,
                                      amount: Number(p.amount_usd).toFixed(2),
                                    })}
                                  </p>
                                  {p.fee_rate != null && p.fee_amount != null && (
                                    <div style={{ marginTop: 8, padding: '8px 10px', background: 'rgba(37,99,235,0.08)', borderRadius: 6, fontSize: 13 }}>
                                      <div>{t('confirmApproveDetails', { fee: Number(p.fee_amount).toFixed(2), feeRate: Number(p.fee_rate).toFixed(2) })}</div>
                                      <div>{t('confirmApproveNet', { net: (Number(p.amount_usd) - Number(p.fee_amount)).toFixed(2) })}</div>
                                    </div>
                                  )}
                                </div>
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleApprove(p.id)} className="bg-green-600 hover:bg-green-700 text-white">
                                {t('confirmApproveBtn')}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>

                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-red-400 text-red-600 hover:bg-red-50" disabled={actionLoading === p.id}>
                              {actionLoading === p.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <><XCircle className="h-3 w-3 mr-1" />{t('actionReject')}</>}
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle className="flex items-center gap-2 text-red-600">
                                <XCircle className="h-5 w-5" />
                                {t('confirmRejectTitle')}
                              </AlertDialogTitle>
                              <AlertDialogDescription>
                                {t('confirmRejectDesc', {
                                  username: p.username ?? t('userIdFallback', { id: p.user_id }),
                                  operation: t(`op_${p.operation}` as Parameters<typeof t>[0]),
                                  asset: p.asset,
                                  amount: Number(p.amount_usd).toFixed(2),
                                })}
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleReject(p.id)} className="bg-red-600 hover:bg-red-700 text-white">
                                {t('confirmRejectBtn')}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ページネーション */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 20 }}>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid #374151', cursor: page <= 1 ? 'default' : 'pointer', opacity: page <= 1 ? 0.4 : 1 }}
          >
            {t('paginationPrev')}
          </button>
          <span style={{ padding: '6px 12px', fontSize: 13, color: '#666' }}>
            {t('paginationInfo', { page, totalPages, total })}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid #374151', cursor: page >= totalPages ? 'default' : 'pointer', opacity: page >= totalPages ? 0.4 : 1 }}
          >
            {t('paginationNext')}
          </button>
        </div>
      )}
    </div>
  )
}

const thStyle: React.CSSProperties = {
  padding: '10px 12px',
  textAlign: 'left',
  fontWeight: 600,
  color: '#d1d5db',
  whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
  verticalAlign: 'middle',
  color: '#e5e7eb',
}

function statusBadgeStyle(s: string): React.CSSProperties {
  const colors: Record<string, { bg: string; color: string }> = {
    pending:  { bg: '#fef3c7', color: '#92400e' },
    approved: { bg: '#dcfce7', color: '#166534' },
    rejected: { bg: '#fee2e2', color: '#991b1b' },
    executed: { bg: '#dbeafe', color: '#1e40af' },
    expired:  { bg: '#f3f4f6', color: '#6b7280' },
  }
  const c = colors[s] ?? { bg: '#f3f4f6', color: '#374151' }
  return {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 12,
    fontSize: 11,
    fontWeight: 600,
    background: c.bg,
    color: c.color,
  }
}
