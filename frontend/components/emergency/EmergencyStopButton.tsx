'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { AlertTriangle, ShieldOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/lib/auth'
import { postJson } from '@/lib/api/http'
import { useAutomationStatus } from '@/components/user/UserProviders'
export function EmergencyStopButton() {
  const t = useTranslations('EmergencyStop')
  const { token } = useAuth()
  const { isStopped, refreshStatus } = useAutomationStatus()
  const [showConfirm, setShowConfirm] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const handleStop = async () => {
    if (!token) return
    setIsLoading(true)
    try {
      await postJson('/api/automation/emergency-stop', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await refreshStatus()
      setShowConfirm(false)
    } catch {
      // fail silently
    } finally {
      setIsLoading(false)
    }
  }

  const handleResume = async () => {
    if (!token) return
    setIsLoading(true)
    try {
      await postJson('/api/automation/emergency-stop/resume', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await refreshStatus()
      setShowConfirm(false)
    } catch {
      // fail silently
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      {/* Floating button — above BottomNav (bottom-nav is h-16 = 64px) */}
      <button
        onClick={() => setShowConfirm(true)}
        className={[
          'fixed bottom-20 right-4 z-50 flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition-all active:scale-95',
          isStopped
            ? 'bg-amber-500 hover:bg-amber-400'
            : 'bg-destructive hover:bg-destructive/90',
        ].join(' ')}
        aria-label={isStopped ? t('floatAriaLabelUnstop') : t('floatAriaLabelStop')}
        title={isStopped ? t('floatAriaLabelUnstop') : t('floatAriaLabelStop')}
      >
        {isStopped ? (
          <ShieldOff className="h-5 w-5 text-white" />
        ) : (
          <AlertTriangle className="h-5 w-5 text-destructive-foreground" />
        )}
      </button>

      {isStopped && (
        <button
          onClick={() => setShowConfirm(true)}
          className="fixed bottom-20 right-[72px] z-50 cursor-pointer"
          aria-label={t('floatAriaLabelUnstop')}
        >
          <span className="rounded bg-amber-500 px-2 py-1 text-xs text-white font-medium">
            {t('floatStoppedLabel')}
          </span>
        </button>
      )}

      {/* Confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-xl bg-background border p-6 shadow-xl">
            {isStopped ? (
              /* ---- Resume dialog ---- */
              <>
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10">
                    <ShieldOff className="h-6 w-6 text-amber-500" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold">{t('resumeDialogTitle')}</h2>
                    <p className="text-xs text-muted-foreground mt-0.5">{t('resumeDialogSubtitle')}</p>
                  </div>
                </div>
                <p className="mb-6 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
                  {t('resumeHealthWarning')}
                </p>
                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => setShowConfirm(false)}
                    disabled={isLoading}
                  >
                    {t('cancelButton')}
                  </Button>
                  <Button
                    className="flex-1 font-bold bg-amber-500 hover:bg-amber-400 text-white"
                    onClick={handleResume}
                    disabled={isLoading}
                  >
                    {isLoading ? t('resumeLoadingButton') : t('resumeButton')}
                  </Button>
                </div>
              </>
            ) : (
              /* ---- Stop dialog ---- */
              <>
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                    <AlertTriangle className="h-6 w-6 text-destructive" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold">{t('stopDialogTitle')}</h2>
                    <p className="text-xs text-muted-foreground mt-0.5">{t('stopDialogSubtitle')}</p>
                  </div>
                </div>
                <p className="mb-6 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                  {t('stopWarningMsg')}
                </p>
                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => setShowConfirm(false)}
                    disabled={isLoading}
                  >
                    {t('cancelButton')}
                  </Button>
                  <Button
                    variant="destructive"
                    className="flex-1 font-bold"
                    onClick={handleStop}
                    disabled={isLoading}
                  >
                    {isLoading ? t('stopLoadingButton') : t('floatStopButton')}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
