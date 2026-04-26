'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useCallback } from 'react'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import {
  listAdminUsersFees,
  listAdminMonthlyEntries,
  getAdminMonthlySummary,
  createAdminRefund,
  buildCsvExportUrl,
} from '@/lib/api/admin-fees'
import type {
  AdminFeeUserRow,
  AdminFeeMonthlyEntry,
  AdminMonthlyAggregate,
} from '@/lib/api/admin-fees'

function currentMonthStr(): string {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  return `${y}-${m}`
}

export default function AdminFeesPage() {
  return (
    <AuthGuard adminOnly>
      <FeesContent />
    </AuthGuard>
  )
}

function FeesContent() {
  const { token } = useAuth()
  const [tab, setTab] = useState<'overview' | 'monthly'>('overview')
  const [month, setMonth] = useState(currentMonthStr())

  const [overviewRows, setOverviewRows] = useState<AdminFeeUserRow[]>([])
  const [monthlyEntries, setMonthlyEntries] = useState<AdminFeeMonthlyEntry[]>([])
  const [monthlySummary, setMonthlySummary] = useState<AdminMonthlyAggregate | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // リファンドモーダル state
  const [refundUserId, setRefundUserId] = useState<number | null>(null)
  const [refundAmount, setRefundAmount] = useState('')
  const [refundReason, setRefundReason] = useState('')
  const [refundLoading, setRefundLoading] = useState(false)
  const [refundError, setRefundError] = useState<string | null>(null)
  const [refundSuccess, setRefundSuccess] = useState<string | null>(null)

  const fetchOverview = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const rows = await listAdminUsersFees(token)
      setOverviewRows(rows)
    } catch (err: unknown) {
      setError(errMsg(err, '手数料一覧の取得に失敗しました'))
    } finally {
      setLoading(false)
    }
  }, [token])

  const fetchMonthly = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [entries, summary] = await Promise.all([
        listAdminMonthlyEntries(token, month),
        getAdminMonthlySummary(token, month),
      ])
      setMonthlyEntries(entries)
      setMonthlySummary(summary)
    } catch (err: unknown) {
      setError(errMsg(err, '月次データの取得に失敗しました'))
    } finally {
      setLoading(false)
    }
  }, [token, month])

  useEffect(() => {
    if (tab === 'overview') {
      fetchOverview()
    } else {
      fetchMonthly()
    }
  }, [tab, fetchOverview, fetchMonthly])

  async function handleRefundSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!token || refundUserId === null) return
    const amt = Number(refundAmount)
    if (isNaN(amt) || amt <= 0) {
      setRefundError('リファンド金額は正の数値を入力してください')
      return
    }
    setRefundLoading(true)
    setRefundError(null)
    setRefundSuccess(null)
    try {
      const res = await createAdminRefund(token, refundUserId, {
        amount: refundAmount,
        reason: refundReason,
      })
      setRefundSuccess(`リファンド完了: ¥${Number(res.refund_amount).toLocaleString()}`)
      setRefundUserId(null)
      setRefundAmount('')
      setRefundReason('')
      if (tab === 'overview') fetchOverview()
      else fetchMonthly()
    } catch (err: unknown) {
      setRefundError(errMsg(err, 'リファンドに失敗しました'))
    } finally {
      setRefundLoading(false)
    }
  }

  return (
    <div style={containerStyle}>
      <h1 style={h1Style}>手数料管理</h1>

      {/* タブ */}
      <div style={tabBarStyle}>
        <button
          onClick={() => setTab('overview')}
          style={tab === 'overview' ? activeTabStyle : inactiveTabStyle}
        >
          ユーザー別サマリー
        </button>
        <button
          onClick={() => setTab('monthly')}
          style={tab === 'monthly' ? activeTabStyle : inactiveTabStyle}
        >
          月次明細
        </button>
      </div>

      {refundSuccess && (
        <div style={successBannerStyle}>
          {refundSuccess}
          <button onClick={() => setRefundSuccess(null)} style={closeBtnStyle}>×</button>
        </div>
      )}

      {error && <div style={errorStyle}>{error}</div>}

      {/* ── ユーザー別サマリータブ ── */}
      {tab === 'overview' && (
        <>
          {loading ? (
            <p style={loadingStyle}>読み込み中...</p>
          ) : (
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>ユーザーID</th>
                    <th style={thStyle}>ユーザー名</th>
                    <th style={thStyle}>メール</th>
                    <th style={thStyle}>ティア</th>
                    <th style={thStyle}>リスクモード</th>
                    <th style={thStyle}>管理報酬累計</th>
                    <th style={thStyle}>成果報酬累計</th>
                    <th style={thStyle}>手数料合計</th>
                    <th style={thStyle}>最終計算日</th>
                    <th style={thStyle}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {overviewRows.length === 0 ? (
                    <tr>
                      <td colSpan={10} style={noDataStyle}>
                        データがありません
                      </td>
                    </tr>
                  ) : (
                    overviewRows.map((r) => (
                      <tr key={r.user_id} style={trStyle}>
                        <td style={tdStyle}>{r.user_id}</td>
                        <td style={tdStyle}>{r.username}</td>
                        <td style={tdStyle}>{r.email}</td>
                        <td style={tdStyle}>{r.tier}</td>
                        <td style={tdStyle}>{r.risk_mode ?? '—'}</td>
                        <td style={{ ...tdStyle, textAlign: 'right' }}>
                          ¥{Number(r.total_management_fee).toLocaleString()}
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right' }}>
                          ¥{Number(r.total_performance_fee).toLocaleString()}
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>
                          ¥{Number(r.total_fee).toLocaleString()}
                        </td>
                        <td style={tdStyle}>{r.last_calculation_date ?? '—'}</td>
                        <td style={tdStyle}>
                          <button
                            onClick={() => {
                              setRefundUserId(r.user_id)
                              setRefundError(null)
                            }}
                            style={refundBtnStyle}
                          >
                            リファンド
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── 月次明細タブ ── */}
      {tab === 'monthly' && (
        <>
          <div style={monthPickerRowStyle}>
            <label style={labelStyle}>対象月:</label>
            <input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              style={monthInputStyle}
            />
            <button onClick={fetchMonthly} style={reloadBtnStyle} disabled={loading}>
              再読み込み
            </button>
            {token && (
              <a
                href={buildCsvExportUrl(token, month)}
                download={`fees_${month}.csv`}
                style={csvLinkStyle}
              >
                CSVエクスポート
              </a>
            )}
          </div>

          {/* 月次サマリーカード */}
          {monthlySummary && (
            <div style={summaryCardRowStyle}>
              <SummaryCard label="管理報酬合計" value={`¥${Number(monthlySummary.total_management_fee).toLocaleString()}`} />
              <SummaryCard label="成果報酬合計" value={`¥${Number(monthlySummary.total_performance_fee).toLocaleString()}`} />
              <SummaryCard label="手数料合計" value={`¥${Number(monthlySummary.total_fee).toLocaleString()}`} highlight />
              <SummaryCard label="対象ユーザー数" value={`${monthlySummary.user_count} 名`} />
              <SummaryCard label="明細件数" value={`${monthlySummary.entry_count} 件`} />
            </div>
          )}

          {loading ? (
            <p style={loadingStyle}>読み込み中...</p>
          ) : (
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>ID</th>
                    <th style={thStyle}>ユーザー名</th>
                    <th style={thStyle}>メール</th>
                    <th style={thStyle}>ティア</th>
                    <th style={thStyle}>リスクモード</th>
                    <th style={thStyle}>計算日</th>
                    <th style={thStyle}>種別</th>
                    <th style={thStyle}>AUM</th>
                    <th style={thStyle}>管理報酬</th>
                    <th style={thStyle}>成果報酬</th>
                    <th style={thStyle}>合計</th>
                  </tr>
                </thead>
                <tbody>
                  {monthlyEntries.length === 0 ? (
                    <tr>
                      <td colSpan={11} style={noDataStyle}>
                        {month} のデータがありません
                      </td>
                    </tr>
                  ) : (
                    monthlyEntries.map((e) => (
                      <tr key={e.id} style={trStyle}>
                        <td style={tdStyle}>{e.id}</td>
                        <td style={tdStyle}>{e.username}</td>
                        <td style={tdStyle}>{e.email}</td>
                        <td style={tdStyle}>{e.tier}</td>
                        <td style={tdStyle}>{e.risk_mode ?? '—'}</td>
                        <td style={tdStyle}>{e.calculation_date}</td>
                        <td style={tdStyle}>
                          <span style={e.period_type === 'refund' ? refundBadgeStyle : periodBadgeStyle}>
                            {e.period_type}
                          </span>
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right' }}>
                          ¥{Number(e.aum_snapshot).toLocaleString()}
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right' }}>
                          ¥{Number(e.management_fee).toLocaleString()}
                        </td>
                        <td style={{ ...tdStyle, textAlign: 'right' }}>
                          ¥{Number(e.performance_fee).toLocaleString()}
                        </td>
                        <td style={{
                          ...tdStyle,
                          textAlign: 'right',
                          fontWeight: 600,
                          color: Number(e.total_fee) < 0 ? '#dc2626' : 'inherit',
                        }}>
                          ¥{Number(e.total_fee).toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── リファンドモーダル ── */}
      {refundUserId !== null && (
        <div style={modalOverlayStyle}>
          <div style={modalStyle}>
            <h2 style={modalTitleStyle}>リファンド処理</h2>
            <p style={{ color: '#555', marginBottom: 12 }}>
              ユーザーID: <strong>{refundUserId}</strong>
            </p>
            <form onSubmit={handleRefundSubmit}>
              <div style={formRowStyle}>
                <label style={labelStyle}>リファンド金額 (円)</label>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={refundAmount}
                  onChange={(e) => setRefundAmount(e.target.value)}
                  required
                  style={inputStyle}
                  placeholder="例: 5000"
                />
              </div>
              <div style={formRowStyle}>
                <label style={labelStyle}>理由</label>
                <textarea
                  value={refundReason}
                  onChange={(e) => setRefundReason(e.target.value)}
                  required
                  rows={3}
                  style={{ ...inputStyle, resize: 'vertical' }}
                  placeholder="リファンド理由を入力してください"
                />
              </div>
              {refundError && <div style={errorStyle}>{refundError}</div>}
              <div style={modalFooterStyle}>
                <button
                  type="button"
                  onClick={() => { setRefundUserId(null); setRefundError(null) }}
                  style={cancelBtnStyle}
                >
                  キャンセル
                </button>
                <button
                  type="submit"
                  disabled={refundLoading}
                  style={submitBtnStyle}
                >
                  {refundLoading ? '処理中...' : 'リファンド実行'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

function SummaryCard({ label, value, highlight = false }: {
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div style={{
      ...summaryCardStyle,
      borderColor: highlight ? '#2563eb' : '#e5e7eb',
      background: highlight ? '#eff6ff' : '#fff',
    }}>
      <div style={summaryLabelStyle}>{label}</div>
      <div style={{ ...summaryValueStyle, color: highlight ? '#1d4ed8' : '#111' }}>{value}</div>
    </div>
  )
}

function errMsg(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'message' in err) return String((err as { message: unknown }).message)
  return fallback
}

// ── Styles ────────────────────────────────────────────────────────────────────

const containerStyle: React.CSSProperties = {
  maxWidth: 1200,
  margin: '0 auto',
  padding: '24px 16px',
}
const h1Style: React.CSSProperties = {
  fontSize: 24,
  fontWeight: 700,
  marginBottom: 20,
}
const tabBarStyle: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  marginBottom: 20,
  borderBottom: '2px solid #e5e7eb',
  paddingBottom: 8,
}
const activeTabStyle: React.CSSProperties = {
  padding: '6px 16px',
  border: 'none',
  borderBottom: '2px solid #2563eb',
  background: 'transparent',
  color: '#2563eb',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: 14,
}
const inactiveTabStyle: React.CSSProperties = {
  padding: '6px 16px',
  border: 'none',
  background: 'transparent',
  color: '#6b7280',
  cursor: 'pointer',
  fontSize: 14,
}
const tableWrapStyle: React.CSSProperties = {
  overflowX: 'auto',
  marginTop: 12,
}
const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 13,
}
const thStyle: React.CSSProperties = {
  padding: '8px 12px',
  textAlign: 'left',
  background: '#f9fafb',
  border: '1px solid #e5e7eb',
  fontWeight: 600,
  whiteSpace: 'nowrap',
}
const tdStyle: React.CSSProperties = {
  padding: '8px 12px',
  border: '1px solid #e5e7eb',
  verticalAlign: 'middle',
}
const trStyle: React.CSSProperties = {}
const noDataStyle: React.CSSProperties = {
  padding: '24px',
  textAlign: 'center',
  color: '#9ca3af',
}
const loadingStyle: React.CSSProperties = {
  color: '#6b7280',
  padding: '16px 0',
}
const errorStyle: React.CSSProperties = {
  padding: '12px 16px',
  background: '#fee2e2',
  color: '#dc2626',
  borderRadius: 6,
  marginBottom: 12,
  fontSize: 14,
}
const successBannerStyle: React.CSSProperties = {
  padding: '12px 16px',
  background: '#d1fae5',
  color: '#065f46',
  borderRadius: 6,
  marginBottom: 12,
  fontSize: 14,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
}
const closeBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  fontSize: 18,
  color: '#065f46',
}
const refundBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  fontSize: 12,
  background: '#fff7ed',
  color: '#c2410c',
  border: '1px solid #fdba74',
  borderRadius: 4,
  cursor: 'pointer',
}
const monthPickerRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  marginBottom: 16,
}
const labelStyle: React.CSSProperties = {
  fontSize: 13,
  color: '#374151',
  fontWeight: 500,
}
const monthInputStyle: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 4,
  padding: '4px 8px',
  fontSize: 14,
}
const reloadBtnStyle: React.CSSProperties = {
  padding: '4px 12px',
  fontSize: 13,
  background: '#f3f4f6',
  border: '1px solid #d1d5db',
  borderRadius: 4,
  cursor: 'pointer',
}
const csvLinkStyle: React.CSSProperties = {
  padding: '4px 12px',
  fontSize: 13,
  background: '#ecfdf5',
  color: '#065f46',
  border: '1px solid #6ee7b7',
  borderRadius: 4,
  textDecoration: 'none',
  display: 'inline-block',
}
const summaryCardRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  marginBottom: 16,
  flexWrap: 'wrap',
}
const summaryCardStyle: React.CSSProperties = {
  flex: '1 1 160px',
  padding: '12px 16px',
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  background: '#fff',
}
const summaryLabelStyle: React.CSSProperties = {
  fontSize: 12,
  color: '#6b7280',
  marginBottom: 4,
}
const summaryValueStyle: React.CSSProperties = {
  fontSize: 20,
  fontWeight: 700,
}
const periodBadgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 6px',
  fontSize: 11,
  background: '#eff6ff',
  color: '#1d4ed8',
  borderRadius: 4,
}
const refundBadgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 6px',
  fontSize: 11,
  background: '#fff7ed',
  color: '#c2410c',
  borderRadius: 4,
}
const modalOverlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.4)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
}
const modalStyle: React.CSSProperties = {
  background: '#fff',
  borderRadius: 8,
  padding: 24,
  width: '100%',
  maxWidth: 440,
  boxShadow: '0 4px 24px rgba(0,0,0,0.2)',
}
const modalTitleStyle: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 700,
  marginBottom: 12,
}
const formRowStyle: React.CSSProperties = {
  marginBottom: 14,
}
const inputStyle: React.CSSProperties = {
  width: '100%',
  border: '1px solid #d1d5db',
  borderRadius: 4,
  padding: '8px 10px',
  fontSize: 14,
  marginTop: 4,
  boxSizing: 'border-box',
}
const modalFooterStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 10,
  marginTop: 16,
}
const cancelBtnStyle: React.CSSProperties = {
  padding: '8px 18px',
  fontSize: 14,
  background: '#f3f4f6',
  border: '1px solid #d1d5db',
  borderRadius: 6,
  cursor: 'pointer',
}
const submitBtnStyle: React.CSSProperties = {
  padding: '8px 18px',
  fontSize: 14,
  background: '#dc2626',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
}
