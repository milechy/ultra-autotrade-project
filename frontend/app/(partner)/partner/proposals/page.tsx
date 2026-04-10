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
import { getStoredToken } from '@/lib/auth'
import {
  fetchAdminProposalStats,
  listAdminProposals,
  approveProposal,
  rejectProposal,
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

  const token = getStoredToken()

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

  const handleApprove = async (id: number) => {
    if (!token) return
    setActionLoading(id)
    try {
      await approveProposal(id, token)
      await loadData()
    } catch {
      setError('承認に失敗しました')
    } finally {
      setActionLoading(null)
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
              borderColor: statusFilter === opt.value ? '#2563eb' : '#ddd',
              background: statusFilter === opt.value ? '#2563eb' : '#fff',
              color: statusFilter === opt.value ? '#fff' : '#333',
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ padding: '10px 16px', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, color: '#dc2626', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#666' }}>
          <Loader2 style={{ width: 24, height: 24, display: 'inline-block' }} className="animate-spin" />
          <p style={{ marginTop: 8 }}>読み込み中...</p>
        </div>
      ) : proposals.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          該当する提案はありません
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #eee', background: '#f9fafb' }}>
                <th style={thStyle}>ユーザー</th>
                <th style={thStyle}>操作</th>
                <th style={thStyle}>アセット</th>
                <th style={thStyle}>金額（USD）</th>
                <th style={thStyle}>理由</th>
                <th style={thStyle}>作成日時</th>
                <th style={thStyle}>ステータス</th>
                <th style={thStyle}>アクション</th>
              </tr>
            </thead>
            <tbody>
              {proposals.map((p) => (
                <tr key={p.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <td style={tdStyle}>{p.username ?? `UID:${p.user_id}`}</td>
                  <td style={tdStyle}>{OPERATION_LABELS[p.operation] ?? p.operation}</td>
                  <td style={tdStyle}>{p.asset}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    ${Number(p.amount_usd).toFixed(2)}
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
                              <AlertDialogDescription>
                                {p.username ?? `ユーザーID: ${p.user_id}`} の{' '}
                                {OPERATION_LABELS[p.operation] ?? p.operation} ({p.asset}・${Number(p.amount_usd).toFixed(2)}) を承認してAave操作を実行します。
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
            style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid #ddd', cursor: page <= 1 ? 'default' : 'pointer', opacity: page <= 1 ? 0.4 : 1 }}
          >
            前へ
          </button>
          <span style={{ padding: '6px 12px', fontSize: 13, color: '#666' }}>
            {page} / {totalPages} ページ（全{total}件）
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid #ddd', cursor: page >= totalPages ? 'default' : 'pointer', opacity: page >= totalPages ? 0.4 : 1 }}
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
  color: '#555',
  whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
  verticalAlign: 'middle',
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
