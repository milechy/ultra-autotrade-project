'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import dynamic from 'next/dynamic'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WalletAddressMask } from '@/components/shared/WalletAddressMask'
import { UserPositions } from './UserPositions'

// recharts は SSR でクラッシュするため dynamic import + ssr: false が必須
const UserHFChart = dynamic(
  () => import('./UserHFChart').then((m) => m.UserHFChart),
  { ssr: false },
)

// ─── Types ────────────────────────────────────────────────────────────────────

type RiskMode = 'conservative' | 'balanced' | 'aggressive'
type UserStatus = 'NORMAL' | 'WARNING' | 'DANGER'
type TradeType = 'SUPPLY' | 'WITHDRAW' | 'BORROW'
type DecisionAction = 'BUY' | 'SELL' | 'HOLD'

interface Position {
  asset: string
  supplied: number
  borrowed: number
  usdValue: number
}

interface HFPoint {
  date: string
  hf: number
}

interface RecentTrade {
  id: string
  type: TradeType
  asset: string
  amount: number
  timestamp: string
}

interface RecentDecision {
  id: string
  action: DecisionAction
  confidence: number
  timestamp: string
}

export interface UserDetail {
  id: string
  address: string
  registeredAt: string
  aum: number
  lastActivity: string
  riskMode: RiskMode
  status: UserStatus
  isPaused: boolean
  positions: Position[]
  healthFactor: number
  hfHistory: HFPoint[]
  recentTrades: RecentTrade[]
  recentDecisions: RecentDecision[]
}

interface UserDetailPanelProps {
  user: UserDetail | null
  onClose: () => void
  onTogglePause: (userId: string, pause: boolean) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ja-JP', {
      timeZone: 'Asia/Tokyo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ja-JP', {
      timeZone: 'Asia/Tokyo',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatUSD(value: number): string {
  return '$' + value.toLocaleString('ja-JP', { maximumFractionDigits: 0 })
}

const RISK_LABELS: Record<RiskMode, string> = {
  conservative: '保守',
  balanced: 'バランス',
  aggressive: '積極',
}

const RISK_COLORS: Record<RiskMode, string> = {
  conservative: 'bg-blue-900/50 text-blue-300 border-blue-800',
  balanced: 'bg-yellow-900/50 text-yellow-300 border-yellow-800',
  aggressive: 'bg-red-900/50 text-red-300 border-red-800',
}

const TRADE_TYPE_COLORS: Record<TradeType, string> = {
  SUPPLY: 'text-green-400',
  WITHDRAW: 'text-orange-400',
  BORROW: 'text-red-400',
}

const DECISION_ACTION_COLORS: Record<DecisionAction, string> = {
  BUY: 'bg-green-900/50 text-green-300',
  SELL: 'bg-red-900/50 text-red-300',
  HOLD: 'bg-gray-700/50 text-gray-400',
}

// ─── Confirm toggle dialog ─────────────────────────────────────────────────────

function ConfirmToggleDialog({
  open,
  isPaused,
  onConfirm,
  onCancel,
}: {
  open: boolean
  isPaused: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const action = isPaused ? '再開' : '停止'
  const actionColor = isPaused
    ? 'bg-green-600 hover:bg-green-700'
    : 'bg-red-600 hover:bg-red-700'

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
      <DialogContent className="max-w-sm bg-gray-900 border-gray-700">
        <DialogHeader>
          <DialogTitle className="text-gray-100">
            ユーザーを{action}しますか？
          </DialogTitle>
          <DialogDescription className="text-gray-400">
            {isPaused
              ? 'このユーザーの自動取引を再開します。'
              : 'このユーザーの自動取引を一時停止します。'}
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2 justify-end pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onCancel}
            className="border-gray-600 text-gray-300 hover:bg-gray-800"
          >
            キャンセル
          </Button>
          <Button
            size="sm"
            onClick={onConfirm}
            className={`text-white ${actionColor}`}
          >
            {action}する
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─── Section heading ──────────────────────────────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
      {children}
    </h3>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function UserDetailPanel({ user, onClose, onTogglePause }: UserDetailPanelProps) {
  const [showConfirm, setShowConfirm] = useState(false)

  function handleToggleClick() {
    setShowConfirm(true)
  }

  function handleConfirm() {
    if (!user) return
    onTogglePause(user.id, !user.isPaused)
    setShowConfirm(false)
  }

  return (
    <>
      <Dialog open={user !== null} onOpenChange={(open) => { if (!open) onClose() }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto bg-gray-950 border-gray-800 text-gray-100">
          <DialogHeader>
            <DialogTitle className="text-gray-100 flex items-center gap-2">
              ユーザー詳細
              {user && (
                <span className={`text-xs px-2 py-0.5 rounded-full border ${
                  user.isPaused
                    ? 'bg-orange-900/50 text-orange-300 border-orange-800'
                    : 'bg-green-900/50 text-green-300 border-green-800'
                }`}>
                  {user.isPaused ? '停止中' : '稼働中'}
                </span>
              )}
            </DialogTitle>
            <DialogDescription className="text-gray-500 text-xs">
              {user ? `登録日: ${formatDate(user.registeredAt)}` : ''}
            </DialogDescription>
          </DialogHeader>

          {user && (
            <div className="space-y-5 text-sm">
              {/* Basic info */}
              <div className="rounded-lg bg-gray-800/60 p-4 space-y-3">
                <SectionHeading>基本情報</SectionHeading>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs text-gray-500 mb-1">ウォレットアドレス</div>
                    <WalletAddressMask address={user.address} chars={10} />
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">AUM</div>
                    <div className="font-semibold text-gray-100">{formatUSD(user.aum)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">リスクモード</div>
                    <span className={`inline-block text-xs px-2 py-0.5 rounded-full border ${RISK_COLORS[user.riskMode]}`}>
                      {RISK_LABELS[user.riskMode]}
                    </span>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">最終アクティビティ</div>
                    <div className="text-gray-300 text-xs">{formatDateTime(user.lastActivity)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">ヘルスファクター</div>
                    <div className={`font-mono font-bold ${
                      user.healthFactor < 1.6 ? 'text-red-400' :
                      user.healthFactor < 2.0 ? 'text-yellow-400' : 'text-green-400'
                    }`}>
                      {user.healthFactor.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">KYCステータス</div>
                    <Badge variant="outline" className="text-xs border-gray-600 text-gray-500">
                      未実装 — Phase 2で対応
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Positions */}
              <div>
                <SectionHeading>ポジション一覧</SectionHeading>
                <UserPositions positions={user.positions} />
              </div>

              {/* HF Chart */}
              <div>
                <SectionHeading>ヘルスファクター推移（直近7日）</SectionHeading>
                <div className="rounded-lg bg-gray-800/60 p-3">
                  <UserHFChart data={user.hfHistory} />
                </div>
              </div>

              {/* Recent trades */}
              <div>
                <SectionHeading>取引履歴（直近5件）</SectionHeading>
                {user.recentTrades.length === 0 ? (
                  <div className="text-xs text-gray-500 py-2 text-center">取引履歴なし</div>
                ) : (
                  <div className="space-y-1.5">
                    {user.recentTrades.map((trade) => (
                      <div
                        key={trade.id}
                        className="flex items-center justify-between rounded-lg bg-gray-800/50 px-3 py-2 text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`font-bold ${TRADE_TYPE_COLORS[trade.type]}`}>
                            {trade.type}
                          </span>
                          <span className="text-gray-300">{trade.asset}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-gray-200">
                            {trade.amount.toLocaleString('ja-JP')}
                          </span>
                          <span className="text-gray-500">{formatDateTime(trade.timestamp)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Recent AI decisions */}
              <div>
                <SectionHeading>AI判定履歴（直近5件）</SectionHeading>
                {user.recentDecisions.length === 0 ? (
                  <div className="text-xs text-gray-500 py-2 text-center">AI判定履歴なし</div>
                ) : (
                  <div className="space-y-1.5">
                    {user.recentDecisions.map((dec) => (
                      <div
                        key={dec.id}
                        className="flex items-center justify-between rounded-lg bg-gray-800/50 px-3 py-2 text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded-full font-bold ${DECISION_ACTION_COLORS[dec.action]}`}>
                            {dec.action}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-gray-300">信頼度 {dec.confidence}%</span>
                          <span className="text-gray-500">{formatDateTime(dec.timestamp)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex justify-end pt-2 border-t border-gray-800">
                <Button
                  size="sm"
                  onClick={handleToggleClick}
                  className={
                    user.isPaused
                      ? 'bg-green-600 hover:bg-green-700 text-white'
                      : 'bg-orange-600 hover:bg-orange-700 text-white'
                  }
                >
                  {user.isPaused ? 'ユーザー再開' : 'ユーザー停止'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {user && (
        <ConfirmToggleDialog
          open={showConfirm}
          isPaused={user.isPaused}
          onConfirm={handleConfirm}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </>
  )
}
