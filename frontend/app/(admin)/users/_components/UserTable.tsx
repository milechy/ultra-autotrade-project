'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { WalletAddressMask } from '@/components/shared/WalletAddressMask'
import type { UserDetail } from './UserDetailPanel'

// ─── Types ────────────────────────────────────────────────────────────────────

type RiskMode = 'conservative' | 'balanced' | 'aggressive'
type UserStatus = 'NORMAL' | 'WARNING' | 'DANGER'

interface UserTableProps {
  users: UserDetail[]
  onSelectUser: (user: UserDetail) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('ja-JP', {
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

const RISK_COLORS: Record<RiskMode, string> = {
  conservative: 'bg-blue-900/50 text-blue-300',
  balanced: 'bg-yellow-900/50 text-yellow-300',
  aggressive: 'bg-red-900/50 text-red-300',
}

const STATUS_COLORS: Record<UserStatus, string> = {
  NORMAL: 'bg-green-900/50 text-green-300',
  WARNING: 'bg-yellow-900/50 text-yellow-300',
  DANGER: 'bg-red-900/50 text-red-300',
}

// ─── Component ────────────────────────────────────────────────────────────────

export function UserTable({ users, onSelectUser }: UserTableProps) {
  const t = useTranslations('AdminUserTable')

  const RISK_LABELS: Record<RiskMode, string> = {
    conservative: t('riskConservative'),
    balanced: t('riskBalanced'),
    aggressive: t('riskAggressive'),
  }

  const STATUS_LABELS: Record<UserStatus, string> = {
    NORMAL: t('statusNormal'),
    WARNING: t('statusWarning'),
    DANGER: t('statusDanger'),
  }

  return (
    <div className="rounded-xl border border-gray-800 overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-gray-900 border-gray-800 hover:bg-gray-900">
            <TableHead className="text-gray-400 font-medium text-xs uppercase tracking-wider">
              {t('colWallet')}
            </TableHead>
            <TableHead className="text-gray-400 font-medium text-xs uppercase tracking-wider">
              {t('colRegistered')}
            </TableHead>
            <TableHead className="text-gray-400 font-medium text-xs uppercase tracking-wider text-right">
              {t('colAum')}
            </TableHead>
            <TableHead className="text-gray-400 font-medium text-xs uppercase tracking-wider">
              {t('colLastActivity')}
            </TableHead>
            <TableHead className="text-gray-400 font-medium text-xs uppercase tracking-wider">
              {t('colRiskMode')}
            </TableHead>
            <TableHead className="text-gray-400 font-medium text-xs uppercase tracking-wider">
              {t('colStatus')}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => (
            <TableRow
              key={user.id}
              onClick={() => onSelectUser(user)}
              className="cursor-pointer border-gray-800 hover:bg-gray-800/60 transition-colors"
            >
              <TableCell className="py-3">
                <div className="flex items-center gap-2">
                  {user.isPaused && (
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-400 flex-shrink-0" title="停止中" />
                  )}
                  <WalletAddressMask address={user.address} chars={6} />
                </div>
              </TableCell>
              <TableCell className="text-gray-400 text-xs py-3">
                {formatDate(user.registeredAt)}
              </TableCell>
              <TableCell className="text-right font-mono text-gray-200 py-3">
                {formatUSD(user.aum)}
              </TableCell>
              <TableCell className="text-gray-400 text-xs py-3">
                {formatDateTime(user.lastActivity)}
              </TableCell>
              <TableCell className="py-3">
                <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${RISK_COLORS[user.riskMode]}`}>
                  {RISK_LABELS[user.riskMode]}
                </span>
              </TableCell>
              <TableCell className="py-3">
                <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[user.status]}`}>
                  {STATUS_LABELS[user.status]}
                </span>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
