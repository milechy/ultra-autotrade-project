'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { ShieldAlert, AlertTriangle } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useAuth } from '@/lib/auth'
import { postJson } from '@/lib/api/http'

type EmergencyStopProps = {
  isStopped: boolean
  onStopped?: () => void
}

export function EmergencyStop({ isStopped, onStopped }: EmergencyStopProps) {
  const { token } = useAuth()
  const t = useTranslations('EmergencyStop')
  const [showConfirm, setShowConfirm] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stopped, setStopped] = useState(isStopped)

  const handleConfirm = async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      await postJson('/automation/emergency-stop', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setStopped(true)
      setShowConfirm(false)
      onStopped?.()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : ''
      setError(t('errorPrefix', { msg }))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      <div className="rounded-xl border-2 border-destructive/30 bg-destructive/5 p-4">
        <div className="mb-3 flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-destructive" />
          <h3 className="font-semibold text-destructive">{t('sectionTitle')}</h3>
        </div>

        {stopped ? (
          <Alert variant="destructive">
            <ShieldAlert className="h-4 w-4" />
            <AlertDescription className="font-medium">
              {t('stoppedMessage')}
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <p className="mb-4 text-sm text-muted-foreground">
              {t('warningText')}
            </p>
            {error && (
              <Alert variant="destructive" className="mb-3">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button
              variant="destructive"
              size="lg"
              className="w-full text-base font-bold"
              onClick={() => setShowConfirm(true)}
              disabled={isLoading}
            >
              <ShieldAlert className="mr-2 h-5 w-5" />
              {t('executeButton')}
            </Button>
          </>
        )}
      </div>

      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-xl bg-background p-6 shadow-xl">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <AlertTriangle className="h-6 w-6 text-destructive" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">{t('dialogTitle')}</h2>
                <p className="text-sm text-muted-foreground">{t('dialogSubtitle')}</p>
              </div>
            </div>
            <p className="mb-6 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {t('dialogDescription')}
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
                onClick={handleConfirm}
                disabled={isLoading}
              >
                {isLoading ? t('stoppingButton') : t('stopButton')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}