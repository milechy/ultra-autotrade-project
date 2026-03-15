'use client'

import { useState } from 'react'
import { AlertTriangle, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { postJson } from '@/lib/api/http'

export function EmergencyStopButton() {
  const { token } = useAuth()
  const [showConfirm, setShowConfirm] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [stopped, setStopped] = useState(false)

  const handleConfirm = async () => {
    if (!token) return
    setIsLoading(true)
    try {
      await postJson('/automation/emergency-stop', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setStopped(true)
      setShowConfirm(false)
    } catch {
      // fail silently, stopped state not set
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      {/* Floating button — above BottomNav (bottom-nav is h-16 = 64px) */}
      <button
        onClick={() => !stopped && setShowConfirm(true)}
        className={[
          'fixed bottom-20 right-4 z-40 flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition-all',
          stopped
            ? 'bg-destructive/40 cursor-not-allowed'
            : 'bg-destructive hover:bg-destructive/90 active:scale-95',
        ].join(' ')}
        aria-label="緊急停止"
        title={stopped ? '停止中' : '緊急停止'}
      >
        {stopped ? (
          <ShieldAlert className="h-5 w-5 text-destructive-foreground/60" />
        ) : (
          <AlertTriangle className="h-5 w-5 text-destructive-foreground" />
        )}
      </button>

      {stopped && (
        <div className="fixed bottom-20 right-16 z-40">
          <span className="rounded bg-destructive/90 px-2 py-1 text-xs text-destructive-foreground font-medium">
            停止中
          </span>
        </div>
      )}

      {/* Confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-xl bg-background border p-6 shadow-xl">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <AlertTriangle className="h-6 w-6 text-destructive" />
              </div>
              <div>
                <h2 className="text-base font-semibold">本当に全ての運用を停止しますか？</h2>
                <p className="text-xs text-muted-foreground mt-0.5">この操作は取り消せません</p>
              </div>
            </div>
            <p className="mb-6 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              全ての自動取引が即時停止されます。再開には管理者の操作が必要です。
            </p>
            <div className="flex gap-3">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => setShowConfirm(false)}
                disabled={isLoading}
              >
                キャンセル
              </Button>
              <Button
                variant="destructive"
                className="flex-1 font-bold"
                onClick={handleConfirm}
                disabled={isLoading}
              >
                {isLoading ? '停止中...' : '停止する'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
