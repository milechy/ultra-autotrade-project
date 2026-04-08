'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Copy, Check } from 'lucide-react'
import { apiPost } from '@/lib/api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

interface InvitationResponse {
  id: number
  code: string
  partner_id: number
  expires_at: string
  max_uses: number
  used_count: number
  created_at: string
  invited_user_id?: number | null
}

export interface InviteModalProps {
  open: boolean
  onClose: () => void
}

// ─── Constants ────────────────────────────────────────────────────────────────

const EXPIRE_OPTIONS = [
  { label: '1日', days: 1 },
  { label: '7日', days: 7 },
  { label: '30日', days: 30 },
]

const MAX_USES_OPTIONS = [1, 5, 10]

// ─── Component ────────────────────────────────────────────────────────────────

export function InviteModal({ open, onClose }: InviteModalProps) {
  const [days, setDays] = useState(7)
  const [maxUses, setMaxUses] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ code: string; url: string } | null>(null)
  const [copied, setCopied] = useState(false)

  function handleClose() {
    setResult(null)
    setError('')
    setDays(7)
    setMaxUses(1)
    setCopied(false)
    onClose()
  }

  async function handleSubmit() {
    setLoading(true)
    setError('')
    try {
      const expiresAt = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString()
      const inv = await apiPost<InvitationResponse>('/api/invitations', {
        expires_at: expiresAt,
        max_uses: maxUses,
      })
      const url = `${window.location.origin}/register?code=${inv.code}`
      setResult({ code: inv.code, url })
    } catch (e: unknown) {
      const err = e as { message?: string }
      setError(err.message ?? '招待コードの発行に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  async function handleCopy() {
    if (!result) return
    await navigator.clipboard.writeText(result.url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose() }}>
      <DialogContent className="max-w-md w-full bg-gray-900 border-gray-700 overflow-hidden focus-visible:ring-0 focus-visible:ring-offset-0">
        <DialogHeader>
          <DialogTitle className="text-gray-100">ユーザーを招待</DialogTitle>
          <DialogDescription className="text-gray-400">
            招待コードを発行してユーザーを招待します。
          </DialogDescription>
        </DialogHeader>

        {!result ? (
          <div className="space-y-4 pt-2">
            {/* Expiry selection */}
            <div>
              <p className="text-xs text-gray-400 mb-2">有効期限</p>
              <div className="flex gap-2">
                {EXPIRE_OPTIONS.map((opt) => (
                  <button
                    key={opt.days}
                    onClick={() => setDays(opt.days)}
                    className={`flex-1 min-w-0 rounded-lg border py-2 text-sm font-medium transition-colors ${
                      days === opt.days
                        ? 'border-blue-500 bg-blue-900/40 text-blue-300'
                        : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Max uses selection */}
            <div>
              <p className="text-xs text-gray-400 mb-2">最大使用回数</p>
              <div className="flex gap-2">
                {MAX_USES_OPTIONS.map((n) => (
                  <button
                    key={n}
                    onClick={() => setMaxUses(n)}
                    className={`flex-1 min-w-0 rounded-lg border py-2 text-sm font-medium transition-colors ${
                      maxUses === n
                        ? 'border-blue-500 bg-blue-900/40 text-blue-300'
                        : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    {n}回
                  </button>
                ))}
              </div>
            </div>

            {error && <p className="text-xs text-red-400">{error}</p>}

            <div className="flex gap-2 justify-end pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleClose}
                className="border-gray-600 text-gray-300 hover:bg-gray-800"
              >
                キャンセル
              </Button>
              <Button
                size="sm"
                onClick={handleSubmit}
                disabled={loading}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                {loading ? '発行中...' : '招待コード発行'}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 pt-2">
            {/* Code display */}
            <div className="rounded-lg bg-gray-800/60 p-4">
              <div className="text-xs text-gray-500 mb-1">招待コード</div>
              <div className="font-mono text-lg text-blue-300 font-bold tracking-widest">
                {result.code}
              </div>
            </div>

            {/* URL + copy */}
            <div>
              <div className="text-xs text-gray-500 mb-1">招待URL</div>
              <div className="flex items-center gap-2">
                <div className="flex-1 min-w-0 rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-xs text-gray-300 font-mono truncate">
                  {result.url}
                </div>
                <Button
                  size="sm"
                  onClick={handleCopy}
                  className={`shrink-0 ${
                    copied
                      ? 'bg-green-600 hover:bg-green-700 text-white'
                      : 'bg-gray-700 hover:bg-gray-600 text-white'
                  }`}
                >
                  {copied ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                size="sm"
                onClick={handleClose}
                className="bg-gray-700 hover:bg-gray-600 text-white"
              >
                閉じる
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
