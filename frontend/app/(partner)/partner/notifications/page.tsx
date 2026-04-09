'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useCallback, useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { getStoredToken } from '@/lib/auth'

// ---- Types ----

interface NotificationLogItem {
  id: number
  channel: string
  severity: string
  title: string
  body: string
  partner_id: number | null
  user_id: number | null
  created_at: string
}

interface NotificationLogPage {
  items: NotificationLogItem[]
  total: number
  page: number
  per_page: number
}

// ---- Helpers ----

function severityBadge(severity: string): React.ReactNode {
  const map: Record<string, { label: string; className: string }> = {
    info:      { label: 'INFO',      className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
    warning:   { label: 'WARNING',   className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
    alert:     { label: 'ALERT',     className: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
    emergency: { label: 'EMERGENCY', className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
  }
  const cfg = map[severity] ?? { label: severity.toUpperCase(), className: 'bg-zinc-100 text-zinc-600' }
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${cfg.className}`}>
      {cfg.label}
    </span>
  )
}

function fmtDatetime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ja-JP', {
      timeZone: 'Asia/Tokyo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

const SEVERITY_OPTIONS = [
  { value: '', label: 'すべて' },
  { value: 'info', label: 'INFO' },
  { value: 'warning', label: 'WARNING' },
  { value: 'alert', label: 'ALERT' },
  { value: 'emergency', label: 'EMERGENCY' },
]

// ---- Page ----

export default function PartnerNotificationsPage() {
  const [data, setData] = useState<NotificationLogPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [severity, setSeverity] = useState('')
  const [page, setPage] = useState(1)
  const perPage = 20

  const load = useCallback(async () => {
    const token = getStoredToken()
    if (!token) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
      if (severity) params.set('severity', severity)
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/api/partner/notifications?${params}`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (!res.ok) throw new Error(`${res.status}`)
      setData(await res.json())
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [page, severity])

  useEffect(() => {
    void load()
  }, [load])

  // severity フィルタ変更時はページをリセット
  function handleSeverityChange(v: string) {
    setSeverity(v)
    setPage(1)
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / perPage)) : 1

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Bell className="h-6 w-6" />
        通知ログ
      </h1>

      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <label className="text-sm text-muted-foreground">重要度:</label>
        <select
          value={severity}
          onChange={(e) => handleSeverityChange(e.target.value)}
          className="text-sm border border-input rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {SEVERITY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {data && (
          <span className="text-xs text-muted-foreground ml-auto">
            全 {data.total} 件
          </span>
        )}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">通知一覧</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 rounded" />
              ))}
            </div>
          ) : !data || data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">
              通知はありません
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">日時</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">重要度</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">タイトル</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">内容</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">チャンネル</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr
                      key={item.id}
                      className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                        {fmtDatetime(item.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        {severityBadge(item.severity)}
                      </td>
                      <td className="px-4 py-3 font-medium">{item.title}</td>
                      <td className="px-4 py-3 text-muted-foreground max-w-xs truncate hidden md:table-cell">
                        {item.body}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs hidden lg:table-cell">
                        {item.channel}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1.5 text-sm border rounded-md disabled:opacity-40 hover:bg-muted transition-colors"
          >
            前へ
          </button>
          <span className="text-sm text-muted-foreground">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1.5 text-sm border rounded-md disabled:opacity-40 hover:bg-muted transition-colors"
          >
            次へ
          </button>
        </div>
      )}
    </div>
  )
}
