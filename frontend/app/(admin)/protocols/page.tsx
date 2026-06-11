'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useCallback } from 'react'
import { RefreshCw } from 'lucide-react'
import AuthGuard from '@/components/AuthGuard'
import PendlePositionCard from '@/components/pendle/PendlePositionCard'

// ── Types ──────────────────────────────────────────────────────────────────

type HealthStatus = 'normal' | 'warning' | 'critical'

interface AaveHealth {
  health_factor: number
  supply_apy: number
  utilization_rate: number
  is_paused: boolean
  is_frozen: boolean
  status: HealthStatus
}

interface LidoHealth {
  peg_ratio: number
  staking_apy: number
  status: HealthStatus
}

interface PendleHealth {
  pt_rate: number
  yt_rate: number
  next_maturity: string
  status: HealthStatus
}

interface ProtocolHealthData {
  aave: AaveHealth
  lido: LidoHealth
  pendle: PendleHealth
  fetched_at: string
}

// ── Mock Data ──────────────────────────────────────────────────────────────

const MOCK_DATA: ProtocolHealthData = {
  aave: {
    health_factor: 1.95,
    supply_apy: 4.2,
    utilization_rate: 72.5,
    is_paused: false,
    is_frozen: false,
    status: 'normal',
  },
  lido: {
    peg_ratio: 99.87,
    staking_apy: 3.8,
    status: 'normal',
  },
  pendle: {
    pt_rate: 95.3,
    yt_rate: 4.7,
    next_maturity: '2026-06-30',
    status: 'warning',
  },
  fetched_at: new Date().toISOString(),
}

// ── Helpers ────────────────────────────────────────────────────────────────

function statusBorderClass(status: HealthStatus): string {
  if (status === 'normal') return 'border-green-500/30 bg-green-500/5'
  if (status === 'warning') return 'border-yellow-500/30 bg-yellow-500/5'
  return 'border-red-500/30 bg-red-500/5'
}

function statusDotClass(status: HealthStatus): string {
  if (status === 'normal') return 'bg-green-400'
  if (status === 'warning') return 'bg-yellow-400'
  return 'bg-red-400'
}

function statusLabel(status: HealthStatus): string {
  if (status === 'normal') return '正常'
  if (status === 'warning') return '警告'
  return '異常'
}

function statusTextClass(status: HealthStatus): string {
  if (status === 'normal') return 'text-green-400'
  if (status === 'warning') return 'text-yellow-400'
  return 'text-red-400'
}

function hfTextClass(hf: number): string {
  if (hf >= 1.8) return 'text-green-400'
  if (hf >= 1.6) return 'text-yellow-400'
  return 'text-red-400'
}

function formatTime(isoStr: string): string {
  return new Date(isoStr).toLocaleTimeString('ja-JP', { timeZone: 'Asia/Tokyo' })
}

// ── Stat Row ──────────────────────────────────────────────────────────────

function StatRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-zinc-800 last:border-0">
      <span className="text-sm text-zinc-500">{label}</span>
      <span className="text-sm font-medium text-zinc-200">{value}</span>
    </div>
  )
}

// ── Card Header ────────────────────────────────────────────────────────────

function ProtocolCardHeader({
  name,
  phase,
  status,
}: {
  name: string
  phase: string
  status: HealthStatus
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h2 className="text-base font-semibold text-zinc-100">{name}</h2>
        <span className="text-xs text-zinc-500">{phase}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`inline-flex h-2 w-2 rounded-full ${statusDotClass(status)}`} />
        <span className={`text-xs font-medium ${statusTextClass(status)}`}>
          {statusLabel(status)}
        </span>
      </div>
    </div>
  )
}

// ── Protocol Cards ─────────────────────────────────────────────────────────

function AaveCard({ data }: { data: AaveHealth }) {
  return (
    <div className={`rounded-xl border p-5 ${statusBorderClass(data.status)}`}>
      <ProtocolCardHeader name="Aave V3" phase="Phase 1 · 稼働中" status={data.status} />
      <StatRow
        label="ヘルスファクター"
        value={<span className={hfTextClass(data.health_factor)}>{data.health_factor.toFixed(2)}</span>}
      />
      <StatRow label="供給APY" value={`${data.supply_apy.toFixed(2)}%`} />
      <StatRow label="利用率" value={`${data.utilization_rate.toFixed(1)}%`} />
      <StatRow
        label="一時停止"
        value={
          <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${
              data.is_paused
                ? 'border-red-500/30 bg-red-500/20 text-red-400'
                : 'border-green-500/30 bg-green-500/20 text-green-400'
            }`}
          >
            {data.is_paused ? '停止中' : '正常'}
          </span>
        }
      />
      <StatRow
        label="凍結"
        value={
          <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${
              data.is_frozen
                ? 'border-red-500/30 bg-red-500/20 text-red-400'
                : 'border-green-500/30 bg-green-500/20 text-green-400'
            }`}
          >
            {data.is_frozen ? '凍結中' : '正常'}
          </span>
        }
      />
    </div>
  )
}

function LidoCard({ data }: { data: LidoHealth }) {
  const pegOk = data.peg_ratio >= 99.5
  return (
    <div className={`rounded-xl border p-5 ${statusBorderClass(data.status)}`}>
      <ProtocolCardHeader name="Lido stETH" phase="Phase 2 · Coming Soon" status={data.status} />
      <StatRow
        label="stETH/ETH ペグ率"
        value={
          <span className={pegOk ? 'text-green-400' : 'text-yellow-400'}>
            {data.peg_ratio.toFixed(2)}%
          </span>
        }
      />
      <StatRow label="ステーキングAPY" value={`${data.staking_apy.toFixed(2)}%`} />
    </div>
  )
}

function PendleCard({ data }: { data: PendleHealth }) {
  return (
    <div className={`rounded-xl border p-5 ${statusBorderClass(data.status)}`}>
      <ProtocolCardHeader name="Pendle PT/YT" phase="Phase 2 · Coming Soon" status={data.status} />
      <StatRow label="PTレート" value={`${data.pt_rate.toFixed(2)}%`} />
      <StatRow label="YTレート" value={`${data.yt_rate.toFixed(2)}%`} />
      <StatRow label="次回満期" value={data.next_maturity} />
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function ProtocolsPage() {
  const [data, setData] = useState<ProtocolHealthData>(MOCK_DATA)
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [isMock, setIsMock] = useState(false)

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/protocols/health')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json() as ProtocolHealthData
      setData(json)
      setIsMock(false)
    } catch {
      setData({ ...MOCK_DATA, fetched_at: new Date().toISOString() })
      setIsMock(true)
    }
    setLastUpdated(new Date().toLocaleTimeString('ja-JP', { timeZone: 'Asia/Tokyo' }))
  }, [])

  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 30_000)
    return () => clearInterval(interval)
  }, [fetchHealth])

  return (
    <AuthGuard adminOnly>
    <div style={{ padding: '1.5rem', maxWidth: 960, margin: '0 auto' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>プロトコルヘルスモニター</h1>
          <p style={{ margin: '6px 0 0', color: '#6b7280', fontSize: 14 }}>
            各プロトコルのリアルタイム稼働状況を監視します（30秒自動更新）
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {lastUpdated && (
            <span style={{ fontSize: 12, color: '#9ca3af' }}>
              最終更新: {lastUpdated}
            </span>
          )}
          <button
            onClick={fetchHealth}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '7px 14px',
              borderRadius: 8,
              border: '1px solid #e5e7eb',
              background: '#fff',
              cursor: 'pointer',
              fontSize: 13,
              color: '#374151',
            }}
          >
            <RefreshCw size={14} />
            更新
          </button>
        </div>
      </div>

      {/* Mock data notice */}
      {isMock && (
        <div style={{
          marginBottom: 16,
          padding: '10px 16px',
          borderRadius: 8,
          background: '#fffbeb',
          border: '1px solid #fcd34d',
          fontSize: 13,
          color: '#92400e',
        }}>
          APIが未実装のため、モックデータを表示しています（GET /api/protocols/health）
        </div>
      )}

      {/* Protocol cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <AaveCard data={data.aave} />
        <LidoCard data={data.lido} />
        <PendleCard data={data.pendle} />
      </div>

      {/* Pendle PT/YT ポジション詳細セクション */}
      <div style={{ marginTop: 24 }}>
        <h2 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>
          Pendle ポジション詳細
        </h2>
        <PendlePositionCard />
      </div>

      <p style={{ marginTop: 16, fontSize: 12, color: '#9ca3af' }}>
        データ取得時刻: {data.fetched_at ? formatTime(data.fetched_at) : '—'}
      </p>
    </div>
    </AuthGuard>
  )
}
