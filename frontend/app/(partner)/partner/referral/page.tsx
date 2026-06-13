'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Copy, TrendingUp, Users } from 'lucide-react'
import { toast } from 'sonner'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getStoredToken } from '@/lib/auth'
import {
  postReferralCode,
  getReferralList,
  getReferralEarnings,
  type ReferralCodeResponse,
  type ReferredUser,
  type ReferralEarnings,
} from '@/lib/api/referral'

function formatJpy(value: string): string {
  const n = Number(value)
  return isNaN(n) ? '—' : `¥${n.toLocaleString('ja-JP', { maximumFractionDigits: 0 })}`
}

function formatRate(value: string): string {
  const n = Number(value)
  return isNaN(n) ? '—' : `${(n * 100).toFixed(0)}%`
}

export default function PartnerReferralPage() {
  const t = useTranslations('PartnerReferral')
  const token = getStoredToken()

  const [codeData, setCodeData] = useState<ReferralCodeResponse | null>(null)
  const [codeLoading, setCodeLoading] = useState(true)
  const [users, setUsers] = useState<ReferredUser[]>([])
  const [usersLoading, setUsersLoading] = useState(true)
  const [earnings, setEarnings] = useState<ReferralEarnings | null>(null)
  const [earningsLoading, setEarningsLoading] = useState(true)

  const loadCode = useCallback(async () => {
    if (!token) return
    setCodeLoading(true)
    try {
      const data = await postReferralCode(token)
      setCodeData(data)
    } catch {
      toast.error(t('errorLoadCode'))
    } finally {
      setCodeLoading(false)
    }
  }, [token, t])

  const loadUsers = useCallback(async () => {
    if (!token) return
    setUsersLoading(true)
    try {
      const data = await getReferralList(token)
      setUsers(data)
    } catch {
      setUsers([])
    } finally {
      setUsersLoading(false)
    }
  }, [token])

  const loadEarnings = useCallback(async () => {
    if (!token) return
    setEarningsLoading(true)
    try {
      const data = await getReferralEarnings(token)
      setEarnings(data)
    } catch {
      setEarnings(null)
    } finally {
      setEarningsLoading(false)
    }
  }, [token])

  useEffect(() => {
    void loadCode()
    void loadUsers()
    void loadEarnings()
  }, [loadCode, loadUsers, loadEarnings])

  const shareUrl = codeData
    ? (typeof window !== 'undefined'
        ? `${window.location.origin}/r/${codeData.referral_code}`
        : codeData.share_url)
    : ''

  const handleCopy = async () => {
    if (!shareUrl) return
    try {
      await navigator.clipboard.writeText(shareUrl)
      toast.success(t('copySuccess'))
    } catch {
      toast.error(t('copyError'))
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold">{t('pageTitle')}</h1>

      {/* Earnings summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1">
              <Users className="h-3.5 w-3.5" />
              {t('referralCount')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {earningsLoading ? (
              <Skeleton className="h-7 w-16 rounded" />
            ) : (
              <p className="text-2xl font-bold">
                {earnings ? t('referralCountValue', { count: earnings.referral_count }) : '—'}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-3.5 w-3.5" />
              {t('monthlyReward')}
              {earnings && (
                <span className="ml-1 text-xs font-normal">
                  {t('monthlyRewardRate', { rate: formatRate(earnings.campaign_rate) })}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {earningsLoading ? (
              <Skeleton className="h-7 w-24 rounded" />
            ) : (
              <p className="text-2xl font-bold">
                {earnings ? formatJpy(earnings.current_month_reward_jpy) : '—'}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              {t('totalPayout')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {earningsLoading ? (
              <Skeleton className="h-7 w-24 rounded" />
            ) : (
              <p className="text-2xl font-bold">
                {earnings ? formatJpy(earnings.total_payout_jpy) : '—'}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* キャンペーン期限バナー */}
      {!earningsLoading && earnings?.campaign_expires_month && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
          {t('campaignExpiry', { month: earnings.campaign_expires_month.slice(0, 7) })}
        </div>
      )}

      {/* Referral code card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('inviteLinkTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {codeLoading ? (
            <Skeleton className="h-10 rounded-md" />
          ) : codeData ? (
            <>
              <div className="flex items-center gap-2 rounded-md border border-input bg-muted px-3 py-2 text-sm font-mono">
                <span className="flex-1 truncate">{shareUrl}</span>
              </div>
              <Button variant="outline" size="sm" onClick={() => { void handleCopy() }} className="gap-2">
                <Copy className="h-4 w-4" />
                {t('copy')}
              </Button>
              <p className="text-xs text-muted-foreground">
                {t('codeLabel')}: <span className="font-mono font-medium">{codeData.referral_code}</span>
              </p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{t('noData')}</p>
          )}
        </CardContent>
      </Card>

      {/* Referred users list */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-4 w-4" />
            {t('referredUsersTitle')}
            {!usersLoading && (
              <span className="text-sm font-normal text-muted-foreground">{t('referredUsersCount', { count: users.length })}</span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {usersLoading ? (
            <div className="p-6 space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded" />
              ))}
            </div>
          ) : users.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">{t('noReferredUsers')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t('colEmail')}</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">{t('colRegisteredAt')}</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">{t('colDetail')}</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr
                      key={u.id}
                      className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3 text-muted-foreground">{u.email_masked}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(u.created_at).toLocaleDateString('ja-JP')}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          href={`/partner/referral/${u.id}`}
                          className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                        >
                          {t('tradeHistory')}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
