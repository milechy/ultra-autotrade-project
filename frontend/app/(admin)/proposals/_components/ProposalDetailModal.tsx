'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import type { AdminProposal } from '@/lib/api/admin-proposals'

interface ProposalDetailModalProps {
  proposal: AdminProposal | null
  onClose: () => void
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
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

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 border-b border-gray-100 dark:border-gray-800 last:border-0">
      <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">{label}</span>
      <span className="text-xs text-gray-800 dark:text-gray-200 text-right break-all">{value}</span>
    </div>
  )
}

export function ProposalDetailModal({ proposal, onClose }: ProposalDetailModalProps) {
  const t = useTranslations('AdminProposalDetailModal')

  const STATUS_LABEL: Record<string, string> = {
    pending: t('statusPending'),
    approved: t('statusApproved'),
    rejected: t('statusRejected'),
    executed: t('statusExecuted'),
    expired: t('statusExpired'),
  }

  return (
    <Dialog open={proposal !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700">
        <DialogHeader>
          <DialogTitle className="text-gray-900 dark:text-gray-100">
            {t('titlePrefix')}{proposal?.id}
          </DialogTitle>
          <DialogDescription className="text-gray-500">
            {proposal?.username ?? `user_${proposal?.user_id}`}
            {proposal?.email && ` · ${proposal.email}`}
          </DialogDescription>
        </DialogHeader>

        {proposal && (
          <div className="space-y-4 text-sm mt-2">
            {/* Status badge */}
            <div className="flex items-center gap-3">
              <Badge variant="outline" className="text-sm px-3 py-1">
                {STATUS_LABEL[proposal.status] ?? proposal.status}
              </Badge>
              <span className="text-xs text-gray-500">{proposal.operation} · {proposal.asset}</span>
            </div>

            {/* Core fields */}
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-0.5">
              <Row label={t('rowAmount')} value={`${Number(proposal.amount).toLocaleString('ja-JP', { maximumFractionDigits: 6 })} ${proposal.asset}`} />
              <Row label={t('rowAmountUsd')} value={`$${Number(proposal.amount_usd).toLocaleString('ja-JP', { maximumFractionDigits: 2 })}`} />
              {proposal.expected_hf_after && (
                <Row label={t('rowExpectedHf')} value={Number(proposal.expected_hf_after).toFixed(4)} />
              )}
              {proposal.estimated_gas_usd && (
                <Row label={t('rowEstimatedGas')} value={`$${Number(proposal.estimated_gas_usd).toFixed(4)}`} />
              )}
              <Row label={t('rowAiDecisionId')} value={proposal.ai_decision_id ?? '—'} />
              <Row label={t('rowCreatedAt')} value={formatDateTime(proposal.created_at)} />
              <Row label={t('rowExpires')} value={formatDateTime(proposal.expires_at)} />
              {proposal.approved_at && <Row label={t('rowApprovedAt')} value={formatDateTime(proposal.approved_at)} />}
              {proposal.rejected_at && <Row label={t('rowRejectedAt')} value={formatDateTime(proposal.rejected_at)} />}
              {proposal.executed_at && <Row label={t('rowExecutedAt')} value={formatDateTime(proposal.executed_at)} />}
            </div>

            {/* Reason */}
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
              <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                {t('sectionReason')}
              </p>
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                {proposal.reason}
              </p>
            </div>

            {/* Tx hash */}
            {proposal.tx_hash && (
              <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                  {t('sectionTxHash')}
                </p>
                <code className="text-xs text-blue-600 dark:text-blue-400 break-all">
                  {proposal.tx_hash}
                </code>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
