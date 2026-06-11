'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
import { useEffect, useState } from 'react'
import { fetchPendlePositions, type PendlePosition, type PendleApyPoint } from '@/lib/api/pendle'

// recharts コンポーネントは SSR クラッシュ防止のため dynamic import 必須 (CLAUDE.md)
const PendleYieldChart = dynamic(() => import('./PendleYieldChart'), { ssr: false })

// ── 残存日数バッジ色 ─────────────────────────────────────────────────────

function maturityBadgeClass(days: number): string {
  if (days > 90) return 'bg-green-500/20 text-green-400 border-green-500/30'
  if (days > 30) return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
  return 'bg-red-500/20 text-red-400 border-red-500/30'
}

// ── 1ポジション分の行 ────────────────────────────────────────────────────

function PositionRow({
  position,
  mockApyHistory,
}: {
  position: PendlePosition
  mockApyHistory: PendleApyPoint[]
}) {
  // Decimal 型文字列 → Number 変換 (CLAUDE.md 標準チェックリスト準拠)
  const ptAmount = Number(position.pt_amount)
  const ytAmount = Number(position.yt_amount)
  const ptPrice = Number(position.pt_price_usd)
  const ytPrice = Number(position.yt_price_usd)
  const apy = Number(position.implied_apy)

  const ptValue = ptAmount * ptPrice
  const ytValue = ytAmount * ytPrice

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
      {/* ヘッダー: 資産名 + 満期バッジ */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-semibold text-zinc-100">
            {position.underlying_asset}
          </span>
          <span className="ml-2 text-xs text-zinc-500">
            満期: {position.maturity}
          </span>
        </div>
        <span
          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${maturityBadgeClass(position.days_to_maturity)}`}
        >
          残存 {position.days_to_maturity} 日
        </span>
      </div>

      {/* PT / YT 数量・価格・評価額 */}
      <div className="grid grid-cols-2 gap-3">
        {/* PT */}
        <div className="rounded-lg bg-zinc-800/50 p-3">
          <p className="text-xs text-zinc-500 mb-1">PT (元本トークン)</p>
          <p className="text-sm font-medium text-zinc-200">
            {ptAmount > 0 ? ptAmount.toFixed(4) : 'データなし'}
          </p>
          {ptAmount > 0 && (
            <>
              <p className="text-xs text-zinc-500">
                単価: ${ptPrice.toFixed(4)}
              </p>
              <p className="text-xs text-indigo-400 font-medium">
                評価額: ${ptValue.toFixed(2)}
              </p>
            </>
          )}
        </div>

        {/* YT */}
        <div className="rounded-lg bg-zinc-800/50 p-3">
          <p className="text-xs text-zinc-500 mb-1">YT (利回りトークン)</p>
          <p className="text-sm font-medium text-zinc-200">
            {ytAmount > 0 ? ytAmount.toFixed(4) : 'データなし'}
          </p>
          {ytAmount > 0 && (
            <>
              <p className="text-xs text-zinc-500">
                単価: ${ytPrice.toFixed(4)}
              </p>
              <p className="text-xs text-indigo-400 font-medium">
                評価額: ${ytValue.toFixed(2)}
              </p>
            </>
          )}
        </div>
      </div>

      {/* APY */}
      <div className="flex items-center justify-between border-t border-zinc-800 pt-2">
        <span className="text-xs text-zinc-500">推定APY</span>
        <span className="text-sm font-semibold text-green-400">
          {apy > 0 ? `${apy.toFixed(2)}%` : 'データなし'}
        </span>
      </div>

      {/* APY 推移チャート */}
      {mockApyHistory.length > 0 && (
        <div className="border-t border-zinc-800 pt-3">
          <PendleYieldChart data={mockApyHistory} title="APY推移 (30日)" />
        </div>
      )}
    </div>
  )
}

// ── メインコンポーネント ──────────────────────────────────────────────────

/**
 * Pendle PT/YT ポジション表示カード
 *
 * - バックエンド API が未実装の場合は「データなし」表示
 * - YieldChart は動的 import で SSR 回避
 */
export default function PendlePositionCard() {
  const [positions, setPositions] = useState<PendlePosition[]>([])
  const [totalValueUsd, setTotalValueUsd] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isFallback, setIsFallback] = useState(false)

  // モック APY 履歴 (バックエンド未実装のため、固定生成せずデータなし扱い)
  const mockApyHistory: PendleApyPoint[] = []

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)

    fetchPendlePositions().then((res) => {
      if (cancelled) return
      if (res === null) {
        setIsFallback(true)
        setPositions([])
      } else {
        setPositions(res.positions ?? [])
        setTotalValueUsd(res.total_value_usd ?? null)
        setIsFallback(false)
      }
      setIsLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [])

  // ローディング中
  if (isLoading) {
    return (
      <div className="rounded-xl border border-zinc-800 p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-zinc-100">
            Pendle PT/YT ポジション
          </h2>
        </div>
        <div className="text-sm text-zinc-500">読み込み中...</div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-zinc-800 p-5 space-y-4">
      {/* カードヘッダー */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-zinc-100">
            Pendle PT/YT ポジション
          </h2>
          <span className="text-xs text-zinc-500">Phase 2 · Coming Soon</span>
        </div>
        {totalValueUsd !== null && (
          <div className="text-right">
            <p className="text-xs text-zinc-500">合計評価額</p>
            <p className="text-sm font-semibold text-zinc-200">
              ${Number(totalValueUsd).toFixed(2)}
            </p>
          </div>
        )}
      </div>

      {/* API 未実装通知 */}
      {isFallback && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-400">
          APIが未実装のため、ポジションデータを取得できません
          （GET /api/protocols/pendle/positions）
        </div>
      )}

      {/* ポジション一覧 */}
      {positions.length === 0 ? (
        <div className="flex items-center justify-center py-8 text-sm text-zinc-500">
          ポジションデータなし
        </div>
      ) : (
        <div className="space-y-3">
          {positions.map((pos) => (
            <PositionRow
              key={pos.id}
              position={pos}
              mockApyHistory={mockApyHistory}
            />
          ))}
        </div>
      )}
    </div>
  )
}
