'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/admin/OracleStatusPanel.tsx
//
// Chainlink / Pyth / Uniswap V3 TWAP 三重 Oracle 検証ステータスパネル。
// - 乖離率バー: 2% 超でオレンジ / 5% 超（HARD_STOP） で赤
// - 全テキストは ja.json キー使用（英語ハードコード禁止）
// - データ未取得時は「データなし」表示（ダミーデータ禁止）

import { useEffect, useState, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { fetchOracleStatus, type OracleAlert } from '@/lib/api/protocols'

// 乖離率 (%) から進捗バーの色を決定する。
// < 2% → 緑 / 2%-5% → オレンジ / 5%+ → 赤
function deviationBarClass(pctStr: string | null): string {
  if (pctStr === null) return 'bg-zinc-600'
  const n = Number(pctStr)
  if (!Number.isFinite(n)) return 'bg-zinc-600'
  if (n >= 5) return 'bg-red-500'
  if (n >= 2) return 'bg-orange-500'
  return 'bg-green-500'
}

// 乖離率の幅（max 100%）
function deviationBarWidth(pctStr: string | null): string {
  if (pctStr === null) return '0%'
  const n = Number(pctStr)
  if (!Number.isFinite(n) || n < 0) return '0%'
  // 10% を上限として正規化
  const capped = Math.min(n, 10)
  return `${(capped / 10) * 100}%`
}

// level → バッジのスタイル
function levelBadgeClass(level: OracleAlert['level']): string {
  switch (level) {
    case 'OK':
      return 'border-green-500/30 bg-green-500/20 text-green-400'
    case 'WARN':
      return 'border-orange-500/30 bg-orange-500/20 text-orange-400'
    case 'HARD_STOP':
      return 'border-red-500/30 bg-red-500/20 text-red-400'
    default:
      return 'border-zinc-600/40 bg-zinc-700/20 text-zinc-400'
  }
}

// 価格文字列を小数点以下6桁に整形。null は「—」
function formatPrice(priceStr: string | null): string {
  if (priceStr === null) return '—'
  const n = Number(priceStr)
  if (!Number.isFinite(n)) return '—'
  return `$${n.toFixed(6)}`
}

// checked_at (ISO 8601) を JST の時刻文字列に変換
function formatCheckedAt(isoStr: string): string {
  const d = new Date(isoStr)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('ja-JP', { timeZone: 'Asia/Tokyo' })
}

type TranslationFn = ReturnType<typeof useTranslations<'AdminProtocols'>>

// 1アセットのアラート行
function OracleAlertRow({ alert, t }: { alert: OracleAlert; t: TranslationFn }) {
  const noData = t('noData')
  const devPct = alert.max_deviation_pct

  return (
    <div className="rounded-lg border border-zinc-700/40 bg-zinc-800/30 p-4 space-y-3">
      {/* ヘッダー: アセット名 + レベルバッジ */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-zinc-100">{alert.asset}</span>
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${levelBadgeClass(alert.level)}`}
        >
          {alert.level === 'OK'
            ? t('oracleLevelOk')
            : alert.level === 'WARN'
              ? t('oracleLevelWarn')
              : t('oracleLevelHardStop')}
        </span>
      </div>

      {/* 乖離率バー */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-zinc-500">{t('oracleDeviation')}</span>
          <span className="text-xs font-medium text-zinc-300">
            {devPct !== null ? `${Number(devPct).toFixed(4)}%` : noData}
          </span>
        </div>
        <div className="h-2 w-full rounded-full bg-zinc-700/50 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${deviationBarClass(devPct)}`}
            style={{ width: deviationBarWidth(devPct) }}
          />
        </div>
      </div>

      {/* 3価格表示 */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <p className="text-[11px] text-zinc-500 mb-0.5">{t('oracleChainlink')}</p>
          <p className="text-xs font-mono text-zinc-200">{formatPrice(alert.chainlink_price)}</p>
        </div>
        <div>
          <p className="text-[11px] text-zinc-500 mb-0.5">{t('oraclePyth')}</p>
          <p className="text-xs font-mono text-zinc-200">{formatPrice(alert.pyth_price)}</p>
        </div>
        <div>
          <p className="text-[11px] text-zinc-500 mb-0.5">{t('oracleTwap')}</p>
          <p className="text-xs font-mono text-zinc-200">{formatPrice(alert.twap_price)}</p>
        </div>
      </div>

      {/* 詳細メッセージ（level != OK の場合のみ表示） */}
      {alert.detail && (
        <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-1">
          {alert.detail}
        </p>
      )}

      {/* 検証日時 */}
      <p className="text-[11px] text-zinc-600">
        {t('oracleCheckedAt')}: {formatCheckedAt(alert.checked_at)}
      </p>
    </div>
  )
}

export default function OracleStatusPanel() {
  const t = useTranslations('AdminProtocols')
  const [alerts, setAlerts] = useState<OracleAlert[]>([])
  const [loadError, setLoadError] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const resp = await fetchOracleStatus()
      setAlerts(resp.alerts)
      setLoadError(false)
    } catch {
      setAlerts([])
      setLoadError(true)
    }
    setLoaded(true)
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30_000)
    return () => clearInterval(interval)
  }, [fetchData])

  return (
    <div className="mt-6">
      <h2 className="text-base font-semibold text-zinc-100 mb-1">{t('oracleStatusTitle')}</h2>
      <p className="text-xs text-zinc-500 mb-4">{t('oracleStatusDescription')}</p>

      {loadError && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-400">
          {t('oracleLoadError')}
        </div>
      )}

      {loaded && !loadError && alerts.length === 0 && (
        <p className="text-sm text-zinc-500">{t('oracleNoAssets')}</p>
      )}

      {alerts.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {alerts.map((alert) => (
            <OracleAlertRow key={alert.asset} alert={alert} t={t} />
          ))}
        </div>
      )}
    </div>
  )
}
