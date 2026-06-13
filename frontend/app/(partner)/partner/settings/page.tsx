'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import { useAuth } from '@/lib/auth'
import { updateUser } from '@/lib/api/users'
import { PasswordChangeCard } from '@/app/(user)/settings/_components/PasswordChangeCard'
import { getStoredToken } from '@/lib/auth'
import { putJson } from '@/lib/api/http'
import { WalletConnectCard } from '@/components/partner/WalletConnectCard'
import { ReferralTab } from '@/components/partner/ReferralTab'

// ---- Profile Card (email + username) ----------------------------------------

function ProfileCard() {
  const t = useTranslations('PartnerSettings')
  const { user, token } = useAuth()
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!token || !user) {
      setError(t('profileErrorNotAuthenticated'))
      return
    }

    const updates: { email?: string; username?: string } = {}
    if (email.trim()) updates.email = email.trim()
    if (username.trim()) updates.username = username.trim()

    if (Object.keys(updates).length === 0) {
      setError(t('profileErrorNoChanges'))
      return
    }

    setIsSubmitting(true)
    try {
      await updateUser(token, user.id, updates)
      toast.success(t('profileUpdateSuccess'))
      setEmail('')
      setUsername('')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : null
      setError(message || t('profileUpdateError'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{t('profileCardTitle')}</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Current values */}
        <div className="mb-4 space-y-1 rounded-lg bg-muted px-3 py-2 text-sm">
          <div className="flex gap-2">
            <span className="text-muted-foreground">{t('profileCurrentEmail')}</span>
            <span className="font-medium">{user?.email ?? '—'}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-muted-foreground">{t('profileCurrentUsername')}</span>
            <span className="font-medium">{user?.username ?? '—'}</span>
          </div>
        </div>

        <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-4">
          {error && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400">
              {error}
            </p>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="new-email" className="text-sm">
              {t('profileNewEmail')}
            </Label>
            <Input
              id="new-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('profileEmailPlaceholder')}
              autoComplete="email"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="new-username" className="text-sm">
              {t('profileNewUsername')}
            </Label>
            <Input
              id="new-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('profileUsernamePlaceholder')}
              autoComplete="username"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? t('profileSubmitting') : t('profileSubmitButton')}
          </button>
        </form>
      </CardContent>
    </Card>
  )
}

// ---- Execution Mode Card ----------------------------------------------------

type ExecutionPolicyValue = 'auto_execute' | 'require_approval' | 'proposal_only'

function ExecutionModeCard() {
  const t = useTranslations('PartnerSettings')
  const { user } = useAuth()
  const token = getStoredToken()
  const [currentPolicy, setCurrentPolicy] = useState<ExecutionPolicyValue | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [pendingPolicy, setPendingPolicy] = useState<ExecutionPolicyValue | null>(null)

  const EXECUTION_POLICY_LABELS: Record<ExecutionPolicyValue, string> = {
    auto_execute: t('policyLabelAutoExecute'),
    require_approval: t('policyLabelRequireApproval'),
    proposal_only: t('policyLabelProposalOnly'),
  }

  const EXECUTION_POLICY_DESCRIPTIONS: Record<ExecutionPolicyValue, string> = {
    auto_execute: t('policyDescAutoExecute'),
    require_approval: t('policyDescRequireApproval'),
    proposal_only: t('policyDescProposalOnly'),
  }

  const EXECUTION_POLICY_DIALOG: Record<ExecutionPolicyValue, string> = {
    auto_execute: t('policyDialogAutoExecute'),
    require_approval: t('policyDialogRequireApproval'),
    proposal_only: t('policyDialogProposalOnly'),
  }

  // useAuth().user.execution_policy をベースに初期値を設定
  useEffect(() => {
    const policy = user?.execution_policy
    if (policy && (policy === 'auto_execute' || policy === 'require_approval' || policy === 'proposal_only')) {
      setCurrentPolicy(policy as ExecutionPolicyValue)
    } else {
      setCurrentPolicy('auto_execute')
    }
  }, [user?.execution_policy])

  const handleConfirm = async () => {
    if (!token || !pendingPolicy) return
    setIsSaving(true)
    try {
      const data = await putJson<{ user_mode: string; execution_policy: string }>('/api/user/settings', {
        execution_policy: pendingPolicy,
      }, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const updated = data.execution_policy as ExecutionPolicyValue
      const validPolicies: ExecutionPolicyValue[] = ['auto_execute', 'require_approval', 'proposal_only']
      setCurrentPolicy(validPolicies.includes(updated) ? updated : 'auto_execute')
      toast.success(t('policySwitchSuccess', { mode: EXECUTION_POLICY_LABELS[pendingPolicy] }))
    } catch {
      toast.error(t('policySwitchError'))
    } finally {
      setIsSaving(false)
      setPendingPolicy(null)
    }
  }

  const allPolicies: ExecutionPolicyValue[] = ['require_approval', 'auto_execute', 'proposal_only']

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{t('executionModeCardTitle')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {currentPolicy === null ? (
          <p className="text-sm text-muted-foreground">{t('executionModeLoading')}</p>
        ) : (
          <>
            <div className="mb-2 text-sm text-muted-foreground">
              {t('executionModeCurrentLabel')}{' '}
              <span className="font-semibold text-foreground">
                {EXECUTION_POLICY_LABELS[currentPolicy]}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {allPolicies.map((policy) => (
                <AlertDialog key={policy} onOpenChange={(open) => { if (!open) setPendingPolicy(null) }}>
                  <AlertDialogTrigger asChild>
                    <button
                      onClick={() => setPendingPolicy(policy)}
                      disabled={currentPolicy === policy || isSaving}
                      className={[
                        'rounded-xl border-2 p-4 text-left transition-colors',
                        currentPolicy === policy
                          ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
                          : 'border-border hover:border-blue-400',
                        'disabled:cursor-not-allowed disabled:opacity-60',
                      ].join(' ')}
                    >
                      <div className="font-semibold text-sm">{EXECUTION_POLICY_LABELS[policy]}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {EXECUTION_POLICY_DESCRIPTIONS[policy]}
                      </div>
                    </button>
                  </AlertDialogTrigger>
                  {pendingPolicy === policy && (
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>
                          {t('policyDialogTitle', { mode: EXECUTION_POLICY_LABELS[policy] })}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {EXECUTION_POLICY_DIALOG[policy]}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>{t('policyDialogCancel')}</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => { void handleConfirm() }}
                          className="bg-blue-600 hover:bg-blue-700 text-white"
                        >
                          {t('policyDialogConfirm')}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  )}
                </AlertDialog>
              ))}
            </div>

            <p className="text-xs text-muted-foreground pt-1">
              {t('executionModeFootnote')}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ---- Page -------------------------------------------------------------------

export default function PartnerSettingsPage() {
  const t = useTranslations('PartnerSettings')
  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold">{t('pageTitle')}</h1>
      <WalletConnectCard />
      <ReferralTab />
      <ExecutionModeCard />
      <ProfileCard />
      <PasswordChangeCard />
    </div>
  )
}
