'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/admin/EModePanel.tsx

/**
 * Aave eMode 最適化パネル（admin 専用）
 *
 * - 現在の eMode カテゴリ / LTV を表示
 * - 推奨 eMode と改善率を表示
 * - admin のみ「eMode 切替」ボタン + 確認ダイアログを表示
 */

import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/lib/auth'
import {
  getEMode,
  setEMode,
  type EModeGetResponse,
  type EModeInfo,
  type EModeRecommendation,
} from '@/lib/api/aave'

// ── Helpers ────────────────────────────────────────────────────────────────

/** bps 文字列 → パーセント文字列 (例: "9000" → "90.00") */
function bpsToPercent(bps: string): string {
  const n = Number(bps)
  if (!Number.isFinite(n)) return '—'
  return (n / 100).toFixed(2)
}

/** ltv_improvement_pct 文字列 → 符号付きパーセント文字列 */
function formatImprovement(pct: string): { text: string; cls: string } {
  const n = Number(pct)
  if (!Number.isFinite(n)) return { text: '—', cls: 'text-zinc-400' }
  const sign = n > 0 ? '+' : ''
  const cls = n > 0 ? 'text-green-400' : n === 0 ? 'text-zinc-400' : 'text-red-400'
  return { text: `${sign}${n.toFixed(2)}%`, cls }
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StatRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-zinc-800 last:border-0 gap-4">
      <span className="text-sm text-zinc-500 shrink-0">{label}</span>
      <span className="text-sm font-medium text-zinc-200 text-right">{value}</span>
    </div>
  )
}

function EModeCard({
  title,
  info,
  t,
}: {
  title: string
  info: EModeInfo
  t: ReturnType<typeof useTranslations<'AdminProtocols'>>
}) {
  const ltvPct = bpsToPercent(info.ltv_bps)
  const ltBps = bpsToPercent(info.liquidation_threshold_bps)

  return (
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-800/30 p-4">
      <p className="text-xs font-semibold text-zinc-400 mb-3">{title}</p>
      <p className="text-base font-bold text-zinc-100 mb-3">{info.label}</p>
      <StatRow
        label={t('emodeLtvLabel')}
        value={
          <span>
            {t('emodeBps', { bps: info.ltv_bps, pct: ltvPct })}
          </span>
        }
      />
      <StatRow
        label="清算閾値"
        value={
          <span>
            {t('emodeBps', { bps: info.liquidation_threshold_bps, pct: ltBps })}
          </span>
        }
      />
    </div>
  )
}

// ── Confirm Dialog ─────────────────────────────────────────────────────────

function ConfirmDialog({
  open,
  onConfirm,
  onCancel,
  switching,
  t,
}: {
  open: boolean
  onConfirm: () => void
  onCancel: () => void
  switching: boolean
  t: ReturnType<typeof useTranslations<'AdminProtocols'>>
}) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      role="dialog"
      aria-modal="true"
    >
      <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-6 max-w-sm w-full mx-4 shadow-xl">
        <h2 className="text-base font-bold text-zinc-100 mb-2">
          {t('emodeSwitchConfirmTitle')}
        </h2>
        <p className="text-sm text-zinc-400 mb-6">{t('emodeSwitchConfirmDesc')}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={switching}
            className="px-4 py-2 rounded-lg border border-zinc-600 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            {t('emodeCancelButton')}
          </button>
          <button
            onClick={onConfirm}
            disabled={switching}
            className="px-4 py-2 rounded-lg bg-blue-600 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {switching ? t('emodeSwitching') : t('emodeConfirmButton')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main Panel ─────────────────────────────────────────────────────────────

export default function EModePanel() {
  const t = useTranslations('AdminProtocols')
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [data, setData] = useState<EModeGetResponse | null>(null)
  const [fetchError, setFetchError] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
  const [switchMessage, setSwitchMessage] = useState<string | null>(null)
  const [switchError, setSwitchError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const res = await getEMode()
      setData(res)
      setFetchError(false)
    } catch {
      setFetchError(true)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleSwitch = useCallback(async () => {
    if (!data) return
    setSwitching(true)
    setSwitchMessage(null)
    setSwitchError(null)
    try {
      const res = await setEMode({
        category_id: data.recommendation.recommended_category_id,
        dry_run: false,
      })
      setSwitchMessage(res.message)
      setConfirmOpen(false)
      // 切替後にデータを再取得
      await fetchData()
    } catch {
      setSwitchError(t('emodeSwitchError'))
    } finally {
      setSwitching(false)
    }
  }, [data, fetchData, t])

  const noChange =
    data !== null &&
    data.recommendation.current_category_id === data.recommendation.recommended_category_id

  return (
    <section className="rounded-xl border border-zinc-700/40 bg-zinc-900/50 p-5 mt-6">
      <h2 className="text-base font-semibold text-zinc-100 mb-4">{t('emodeTitle')}</h2>

      {fetchError && (
        <p className="text-sm text-red-400 mb-4">{t('emodeFetchError')}</p>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <EModeCard
              title={t('emodeCurrentLabel')}
              info={data.current_emode}
              t={t}
            />
            <EModeCard
              title={t('emodeRecommendedLabel')}
              info={{
                category_id: data.recommendation.recommended_category_id,
                // ラベルは category_id から ja.json キーで解決
                label:
                  data.recommendation.recommended_category_id === 0
                    ? t('emodeCategory0')
                    : data.recommendation.recommended_category_id === 1
                      ? t('emodeCategory1')
                      : t('emodeCategory2'),
                ltv_bps: data.recommendation.recommended_ltv_bps,
                liquidation_threshold_bps: data.current_emode.liquidation_threshold_bps,
              }}
              t={t}
            />
          </div>

          {/* LTV 改善率 */}
          <div className="mb-4 rounded-lg border border-zinc-700/50 bg-zinc-800/20 px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-zinc-500">{t('emodeImprovementLabel')}</span>
              <span
                className={`text-sm font-bold ${formatImprovement(data.recommendation.ltv_improvement_pct).cls}`}
              >
                {formatImprovement(data.recommendation.ltv_improvement_pct).text}
              </span>
            </div>
            <p className="text-xs text-zinc-500 mt-2">{data.recommendation.reason}</p>
            {data.recommendation.collateral_assets.length > 0 && (
              <p className="text-xs text-zinc-600 mt-1">
                {t('emodeCollateralLabel')}: {data.recommendation.collateral_assets.join(', ')}
              </p>
            )}
          </div>

          {/* 切替メッセージ */}
          {switchMessage && (
            <p className="text-sm text-green-400 mb-3">{switchMessage}</p>
          )}
          {switchError && (
            <p className="text-sm text-red-400 mb-3">{switchError}</p>
          )}

          {/* admin のみ切替ボタン */}
          {isAdmin && (
            <div className="flex justify-end">
              {noChange ? (
                <span className="text-sm text-zinc-500">{t('emodeNoChange')}</span>
              ) : (
                <button
                  onClick={() => setConfirmOpen(true)}
                  disabled={switching}
                  className="px-4 py-2 rounded-lg bg-blue-600 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
                >
                  {t('emodeSwitchButton')}
                </button>
              )}
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onConfirm={handleSwitch}
        onCancel={() => setConfirmOpen(false)}
        switching={switching}
        t={t}
      />
    </section>
  )
}
