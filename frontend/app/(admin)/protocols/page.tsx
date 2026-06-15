'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useCallback } from 'react'
import { RefreshCw } from 'lucide-react'
import { useTranslations } from 'next-intl'
import AuthGuard from '@/components/AuthGuard'
import {
  fetchProtocolsHealth,
  type ProtocolHealth,
  type RiskLevel,
} from '@/lib/api/protocols'
import PendlePositionCard from '@/components/pendle/PendlePositionCard'
import OracleStatusPanel from '@/components/admin/OracleStatusPanel'
import PoolHealthPanel from '@/components/admin/PoolHealthPanel'
import BorrowRatesPanel from '@/components/admin/BorrowRatesPanel'

// ── Static protocol metadata (表示順 / 表示名 / フェーズ) ──────────────────
// risk_level / tvl_usd / is_operational / alerts は API から取得する。
// ダミーの数値は一切持たない（CLAUDE.md チェックリスト: ハードコードデータ禁止）。

interface ProtocolMeta {
  protocol: string // API の protocol キー (aave / lido / pendle)
  nameKey: string
  phaseKey: string
}

const PROTOCOL_META: ProtocolMeta[] = [
  { protocol: 'aave', nameKey: 'protocolNameAave', phaseKey: 'phaseAave' },
  { protocol: 'lido', nameKey: 'protocolNameLido', phaseKey: 'phaseLido' },
  { protocol: 'pendle', nameKey: 'protocolNamePendle', phaseKey: 'phasePendle' },
]

// ── Helpers ────────────────────────────────────────────────────────────────

// risk_level (low/medium/high/critical) → 色・ラベルの既存 UI 慣習踏襲
// LOW=緑 / MEDIUM=黄 / HIGH=橙 / CRITICAL=赤
function riskBorderClass(risk: RiskLevel | null): string {
  switch (risk) {
    case 'low':
      return 'border-green-500/30 bg-green-500/5'
    case 'medium':
      return 'border-yellow-500/30 bg-yellow-500/5'
    case 'high':
      return 'border-orange-500/30 bg-orange-500/5'
    case 'critical':
      return 'border-red-500/30 bg-red-500/5'
    default:
      return 'border-zinc-700/40 bg-zinc-800/20'
  }
}

function riskDotClass(risk: RiskLevel | null): string {
  switch (risk) {
    case 'low':
      return 'bg-green-400'
    case 'medium':
      return 'bg-yellow-400'
    case 'high':
      return 'bg-orange-400'
    case 'critical':
      return 'bg-red-400'
    default:
      return 'bg-zinc-500'
  }
}

function riskTextClass(risk: RiskLevel | null): string {
  switch (risk) {
    case 'low':
      return 'text-green-400'
    case 'medium':
      return 'text-yellow-400'
    case 'high':
      return 'text-orange-400'
    case 'critical':
      return 'text-red-400'
    default:
      return 'text-zinc-400'
  }
}

// tvl_usd は Decimal 文字列。Number() でラップし、"0" / 空 / NaN は「データなし」。
function formatTvl(tvlUsd: string | undefined, noData: string): string {
  if (tvlUsd === undefined || tvlUsd === '') return noData
  const n = Number(tvlUsd)
  if (!Number.isFinite(n) || n === 0) return noData
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `$${(n / 1_000).toFixed(2)}K`
  return `$${n.toFixed(0)}`
}

// tvl_change_24h_pct (Decimal 文字列) を符号付きで整形。取得不能時は「データなし」。
function formatTvlChange(
  pct: string | undefined,
  noData: string,
): { text: string; cls: string } {
  if (pct === undefined || pct === '') return { text: noData, cls: 'text-zinc-500' }
  const n = Number(pct)
  if (!Number.isFinite(n)) return { text: noData, cls: 'text-zinc-500' }
  const sign = n > 0 ? '+' : ''
  const cls = n > 0 ? 'text-green-400' : n < 0 ? 'text-red-400' : 'text-zinc-300'
  return { text: `${sign}${n.toFixed(2)}%`, cls }
}

function formatTime(isoStr: string | undefined): string {
  if (!isoStr) return '—'
  const d = new Date(isoStr)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('ja-JP', { timeZone: 'Asia/Tokyo' })
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
  risk,
  riskLabelText,
}: {
  name: string
  phase: string
  risk: RiskLevel | null
  riskLabelText: string
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h2 className="text-base font-semibold text-zinc-100">{name}</h2>
        <span className="text-xs text-zinc-500">{phase}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`inline-flex h-2 w-2 rounded-full ${riskDotClass(risk)}`} />
        <span className={`text-xs font-medium ${riskTextClass(risk)}`}>{riskLabelText}</span>
      </div>
    </div>
  )
}

// ── Operational Badge ──────────────────────────────────────────────────────

function OperationalBadge({
  isOperational,
  labelNoData,
  labelOperational,
  labelStopped,
}: {
  isOperational: boolean | null
  labelNoData: string
  labelOperational: string
  labelStopped: string
}) {
  if (isOperational === null) {
    return (
      <span className="inline-flex items-center rounded-full border border-zinc-600/40 bg-zinc-700/20 px-2 py-0.5 text-xs font-semibold text-zinc-400">
        {labelNoData}
      </span>
    )
  }
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${
        isOperational
          ? 'border-green-500/30 bg-green-500/20 text-green-400'
          : 'border-red-500/30 bg-red-500/20 text-red-400'
      }`}
    >
      {isOperational ? labelOperational : labelStopped}
    </span>
  )
}

// ── Protocol Card ──────────────────────────────────────────────────────────

function ProtocolCard({
  meta,
  health,
  t,
}: {
  meta: ProtocolMeta
  health: ProtocolHealth | null
  t: ReturnType<typeof useTranslations<'AdminProtocols'>>
}) {
  const risk = health?.risk_level ?? null
  const noData = t('noData')
  const change = formatTvlChange(health?.tvl_change_24h_pct, noData)
  const alerts = health?.alerts ?? []

  const riskLabelText = risk
    ? t(`riskLabel_${risk}` as Parameters<typeof t>[0])
    : noData

  return (
    <div className={`rounded-xl border p-5 ${riskBorderClass(risk)}`}>
      <ProtocolCardHeader
        name={t(meta.nameKey as Parameters<typeof t>[0])}
        phase={t(meta.phaseKey as Parameters<typeof t>[0])}
        risk={risk}
        riskLabelText={riskLabelText}
      />

      <StatRow
        label={t('statOperational')}
        value={
          <OperationalBadge
            isOperational={health?.is_operational ?? null}
            labelNoData={noData}
            labelOperational={t('operational')}
            labelStopped={t('stopped')}
          />
        }
      />
      <StatRow
        label={t('statTvl')}
        value={<span className="text-zinc-200">{formatTvl(health?.tvl_usd, noData)}</span>}
      />
      <StatRow
        label={t('statTvlChange24h')}
        value={<span className={change.cls}>{change.text}</span>}
      />
      <StatRow
        label={t('statRiskLevel')}
        value={<span className={riskTextClass(risk)}>{riskLabelText}</span>}
      />

      {/* アラート一覧（API 由来）。なければ「アラートなし」 */}
      <div className="mt-3">
        <p className="text-xs font-medium text-zinc-500 mb-1.5">{t('alerts')}</p>
        {alerts.length === 0 ? (
          <p className="text-xs text-zinc-600">{t('noAlerts')}</p>
        ) : (
          <ul className="space-y-1">
            {alerts.map((alert, i) => (
              <li
                key={i}
                className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-1"
              >
                {alert}
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="mt-3 text-[11px] text-zinc-600">
        {t('lastChecked', { time: formatTime(health?.last_checked) })}
      </p>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function ProtocolsPage() {
  const t = useTranslations('AdminProtocols')

  // protocol キー → ProtocolHealth の map
  const [healthMap, setHealthMap] = useState<Record<string, ProtocolHealth>>({})
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [loadError, setLoadError] = useState(false)

  const fetchHealth = useCallback(async () => {
    try {
      const list = await fetchProtocolsHealth()
      const map: Record<string, ProtocolHealth> = {}
      for (const item of list) {
        map[item.protocol] = item
      }
      setHealthMap(map)
      setLoadError(false)
    } catch {
      // 取得失敗時はモックを表示しない（CLAUDE.md チェックリスト: 黙示モック禁止）。
      // 既存データはクリアし「データ取得失敗」を明示する。
      setHealthMap({})
      setLoadError(true)
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
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
            flexWrap: 'wrap',
            marginBottom: 24,
          }}
        >
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>{t('pageTitle')}</h1>
            <p style={{ margin: '6px 0 0', color: '#6b7280', fontSize: 14 }}>
              {t('pageDescription')}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            {lastUpdated && (
              <span style={{ fontSize: 12, color: '#9ca3af' }}>
                {t('lastUpdated', { time: lastUpdated })}
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
              {t('refresh')}
            </button>
          </div>
        </div>

        {/* データ取得失敗の通知（モックは表示しない） */}
        {loadError && (
          <div
            style={{
              marginBottom: 16,
              padding: '10px 16px',
              borderRadius: 8,
              background: '#fef2f2',
              border: '1px solid #fca5a5',
              fontSize: 13,
              color: '#991b1b',
            }}
          >
            {t('loadError')}
          </div>
        )}

        {/* Protocol cards grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {PROTOCOL_META.map((meta) => (
            <ProtocolCard
              key={meta.protocol}
              meta={meta}
              health={healthMap[meta.protocol] ?? null}
              t={t}
            />
          ))}
        </div>

        {/* Pendle PT/YT ポジション詳細セクション (#624 統合) */}
        <div style={{ marginTop: 24 }}>
          <h2 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>
            {t('pendlePositionTitle')}
          </h2>
          <PendlePositionCard />
        </div>

        {/* Oracle 多重検証ステータスパネル（rsETH/srsETH 再発防止） */}
        <OracleStatusPanel />

        {/* Aave プール赤字監視（LiquidationSentinel） */}
        <div style={{ marginTop: 24 }}>
          <h2 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>
            {t('poolHealthTitle')}
          </h2>
          <PoolHealthPanel />
        </div>

        {/* GHO / USDC 借入金利比較パネル */}
        <div style={{ marginTop: 24 }}>
          <BorrowRatesPanel />
        </div>
      </div>
    </AuthGuard>
  )
}
