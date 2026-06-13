'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { listAdminProposals } from '@/lib/api/admin-proposals'
import type { AdminProposal } from '@/lib/api/admin-proposals'
import {
  ProposalKPIs,
  ProposalFilters,
  ProposalTable,
  ProposalDetailModal,
} from './_components'
import type { ProposalFiltersState } from './_components'

const DEFAULT_FILTERS: ProposalFiltersState = {
  status: 'ALL',
  operation: 'ALL',
  userSearch: '',
  dateFrom: '',
  dateTo: '',
}

function applyClientFilters(proposals: AdminProposal[], filters: ProposalFiltersState): AdminProposal[] {
  return proposals.filter((p) => {
    if (filters.operation !== 'ALL' && p.operation !== filters.operation) return false
    if (filters.userSearch) {
      const q = filters.userSearch.toLowerCase()
      const matchUser = (p.username ?? '').toLowerCase().includes(q)
      const matchEmail = (p.email ?? '').toLowerCase().includes(q)
      if (!matchUser && !matchEmail) return false
    }
    return true
  })
}

export default function ProposalsPage() {
  return (
    <AuthGuard adminOnly>
      <ProposalsContent />
    </AuthGuard>
  )
}

function ProposalsContent() {
  const { token } = useAuth()
  const t = useTranslations('AdminProposals')

  const [proposals, setProposals] = useState<AdminProposal[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<ProposalFiltersState>(DEFAULT_FILTERS)
  const [page, setPage] = useState(1)
  const [selectedProposal, setSelectedProposal] = useState<AdminProposal | null>(null)
  const fetchProposals = useCallback(
    async (f: ProposalFiltersState, p: number) => {
      if (!token) return
      setLoading(true)
      setError(null)
      try {
        const res = await listAdminProposals(token, {
          status: f.status !== 'ALL' ? f.status : undefined,
          date_from: f.dateFrom || undefined,
          date_to: f.dateTo || undefined,
          page: p,
          limit: 20,
        })
        setProposals(res.items)
        setTotal(res.total)
      } catch (err: unknown) {
        const msg = err && typeof err === 'object' && 'message' in err
          ? String((err as { message: unknown }).message)
          : t('fetchError')
        setError(msg)
      } finally {
        setLoading(false)
      }
    },
    [token, t]
  )

  // Initial load
  useEffect(() => {
    fetchProposals(DEFAULT_FILTERS, 1)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  function handleFilterChange(next: ProposalFiltersState) {
    setFilters(next)
    setPage(1)
    fetchProposals(next, 1)
  }

  function handlePageChange(p: number) {
    setPage(p)
    fetchProposals(filters, p)
  }

  const displayed = useMemo(
    () => applyClientFilters(proposals, filters),
    [proposals, filters]
  )

  return (
    <>
      <title>{t('pageTitle')}</title>

      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
            {t('heading')}
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t('description')}
          </p>
        </div>
        <button
          onClick={() => fetchProposals(filters, page)}
          className="px-4 py-2 text-sm font-medium bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
        >
          {t('reload')}
        </button>
      </div>

      {/* KPIs — fetches /api/proposals/admin/stats independently */}
      <div className="mb-6">
        <ProposalKPIs />
      </div>

      {/* Filters */}
      <div className="mb-4">
        <ProposalFilters filters={filters} onChange={handleFilterChange} />
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 p-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="mb-4 text-sm text-gray-500 text-center py-4">{t('loading')}</div>
      )}

      {/* Table */}
      {!loading && (
        <ProposalTable
          proposals={displayed}
          page={page}
          total={total}
          onPageChange={handlePageChange}
          onRowClick={setSelectedProposal}
        />
      )}

      {/* Detail modal */}
      <ProposalDetailModal
        proposal={selectedProposal}
        onClose={() => setSelectedProposal(null)}
      />
    </>
  )
}
