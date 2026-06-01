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
import { ethers } from 'ethers'
import { getStoredToken } from '@/lib/auth'
import {
  fetchAdminProposalStats,
  listAdminProposals,
  rejectProposal,
  buildPartnerTx,
  submitPartnerTx,
  type AdminProposal,
  type AdminProposalStats,
} from '@/lib/api/admin-proposals'

const STATUS_LABELS: Record<string, string> = {
  pending: '承認待ち',
  approved: '承認済み',
  rejected: '拒否済み',
  executed: '実行済み',
  expired: '期限切れ',
}

const OPERATION_LABELS: Record<string, string> = {
  SUPPLY: '預入（SUPPLY）',
  WITHDRAW: '引出（WITHDRAW）',
  BORROW: '借入（BORROW）',
  REPAY: '返済（REPAY）',
}

const FILTER_OPTIONS = [
  { value: '', label: 'すべて' },
  { value: 'pending', label: '承認待ち' },
  { value: 'approved', label: '承認済み' },
  { value: 'rejected', label: '拒否済み' },
  { value: 'executed', label: '実行済み' },
]

export default function PartnerProposalsPage() {
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
      setError('データの取得に失敗しました')
    } finally {
      setIsLoading(false)
    }
  }, [token, statusFilter, page])

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
    // embedded wallet (Privy TEE) のみ使用。外部 wallet (MetaMask 等) は秘密鍵がサーバーに渡る
    // 懸念があるため除外。walletClientType === 'privy' が Privy embedded wallet の識別子。
    const wallet = wallets.find(w => w.walletClientType === 'privy') ?? null
    if (!wallet) {
      setError('Privy embedded wallet が見つかりません。Privy メールアドレスでログインしてください（MetaMask 等の外部 wallet は使用不可）。')
      return
    }

    setActionLoading(id)
    setSigningStep(null)
    setError(null)

    try {
      // Step 1: 未署名 tx をサーバーから取得
      setSigningStep('トランザクションを準備中...')
      const txData = await buildPartnerTx(id, token)

      // EIP-1193 プロバイダー取得 (Privy が署名ポップアップを表示)
      const eip1193 = await wallet.getEthereumProvider()
      const ethProvider = new ethers.BrowserProvider(eip1193 as ethers.Eip1193Provider)

      let finalTxHash: string

      if (txData.operation === 'SUPPLY' && txData.approve_tx && txData.supply_tx) {
        // SUPPLY: approve → supply の順に署名・送信
        setSigningStep('Step 1/2: USDC approve に署名してください...')
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
        setSigningStep('approve 確認中...')
        const approveReceipt = await ethProvider.waitForTransaction(approveTxHash)
        if (approveReceipt === null || approveReceipt.status === 0) {
          throw new Error('approve トランザクションが revert しました。残高・ガス代を確認してください。')
        }

        setSigningStep('Step 2/2: Aave supply に署名してください...')
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
        setSigningStep('Aave withdraw に署名してください...')
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
        throw new Error(`未対応の operation: ${txData.operation}`)
      }

      // Step 3: tx_hash をバックエンドに報告
      setSigningStep('完了を記録中...')
      await submitPartnerTx(id, finalTxHash, txData.wallet_address, token)
      await loadData()

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      // ユーザーキャンセルは正常操作
      if (msg.includes('User rejected') || msg.includes('user rejected')) {
        setError('署名がキャンセルされました')
      } else {
        setError(`承認に失敗しました: ${msg}`)
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
      setError('拒否に失敗しました')
    } finally {
      setActionLoading(null)
    }
  }

  const totalPages = Math.ceil(total / 20)

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center', gap: 10 }}>
        <ClipboardList style={{ width: 24, height: 24, color: '#2563eb' }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>AI提案管理</h1>
      </div>

      {/* KPI カード */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>承認待ち</CardTitle>
            </CardHeader>
            <CardContent>
              <span style={{ fontSize: 28, fontWeight: 700, color: '#d97706' }}>{stats.pending}</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>本日承認</CardTitle>
            </CardHeader>
            <CardContent>
              <span style={{ fontSize: 28, fontWeight: 700, color: '#16a34a' }}>{stats.today_approved}</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>本日拒否</CardTitle>
            </CardHeader>
            <CardContent>
              <span style={{ fontSize: 28, fontWeight: 700, color: '#dc2626' }}>{stats.today_rejected}</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader style={{ paddingBottom: 4 }}>
              <CardTitle style={{ fontSize: 13, color: '#666' }}>期限切れ</CardTitle>
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
          <p style={{ marginTop: 8, color: '#9ca3af' }}>読み込み中...</p>
        </div>
      ) : proposals.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
          該当する提案はありません
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #374151', background: 'rgba(255,255,255,0.04)' }}>
                <th style={thStyle}>ユーザー</th>
                <th style={thStyle}>操作</th>
                <th style={thStyle}>アセット</th>
                <th style={thStyle}>金額（USD）</th>
                <th style={thStyle}>手数料率</th>
                <th style={thStyle}>手数料額</th>
                <th style={thStyle}>理由</th>
                <th style={thStyle}>作成日時</th>
                <th style={thStyle}>ステータス</th>
                <th style={thStyle}>アクション</th>
              </tr>
            </thead>
            <tbody>
              {proposals.map((p) => (
                <tr key={p.id} style={{ borderBottom: '1px solid #374151' }}>
                  <td style={tdStyle}>{p.username ?? `UID:${p.user_id}`}</td>
                  <td style={tdStyle}>{OPERATION_LABELS[p.operation] ?? p.operation}</td>
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
                  <td style={tdStyle}>{new Date(p.created_at).toLocaleString('ja-JP')}</td>
                  <td style={tdStyle}>
                    <span style={statusBadgeStyle(p.status)}>
                      {STATUS_LABELS[p.status] ?? p.status}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                    {p.status === 'pending' && (
                      <div style={{ display: 'flex', gap: 6 }}>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-green-500 text-green-700 hover:bg-green-50" disabled={actionLoading === p.id}>
                              {actionLoading === p.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <><CheckCircle className="h-3 w-3 mr-1" />承認</>}
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle className="flex items-center gap-2">
                                <CheckCircle className="h-5 w-5 text-green-600" />
                                提案を承認しますか？
                              </AlertDialogTitle>
                              <AlertDialogDescription asChild>
                                <div>
                                  <p>
                                    {p.username ?? `ユーザーID: ${p.user_id}`} の{' '}
                                    {OPERATION_LABELS[p.operation] ?? p.operation} ({p.asset}・${Number(p.amount_usd).toFixed(2)}) を承認してAave操作を実行します。
                                  </p>
                                  {p.fee_rate != null && p.fee_amount != null && (
                                    <div style={{ marginTop: 8, padding: '8px 10px', background: 'rgba(37,99,235,0.08)', borderRadius: 6, fontSize: 13 }}>
                                      <div>手数料: ${Number(p.fee_amount).toFixed(2)}（{Number(p.fee_rate).toFixed(2)}%）</div>
                                      <div>実行金額: ${(Number(p.amount_usd) - Number(p.fee_amount)).toFixed(2)}（手数料控除後）</div>
                                    </div>
                                  )}
                                </div>
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>キャンセル</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleApprove(p.id)} className="bg-green-600 hover:bg-green-700 text-white">
                                承認する
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>

                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-red-400 text-red-600 hover:bg-red-50" disabled={actionLoading === p.id}>
                              {actionLoading === p.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <><XCircle className="h-3 w-3 mr-1" />拒否</>}
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle className="flex items-center gap-2 text-red-600">
                                <XCircle className="h-5 w-5" />
                                提案を拒否しますか？
                              </AlertDialogTitle>
                              <AlertDialogDescription>
                                {p.username ?? `ユーザーID: ${p.user_id}`} の{' '}
                                {OPERATION_LABELS[p.operation] ?? p.operation} ({p.asset}・${Number(p.amount_usd).toFixed(2)}) を拒否します。この操作は取り消せません。
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>キャンセル</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleReject(p.id)} className="bg-red-600 hover:bg-red-700 text-white">
                                拒否する
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
            前へ
          </button>
          <span style={{ padding: '6px 12px', fontSize: 13, color: '#666' }}>
            {page} / {totalPages} ページ（全{total}件）
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid #374151', cursor: page >= totalPages ? 'default' : 'pointer', opacity: page >= totalPages ? 0.4 : 1 }}
          >
            次へ
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
