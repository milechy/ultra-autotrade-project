'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/signup/page.tsx
// 一般公開ユーザー登録ページ（partner 招待・紹介コード不要）。
// backend POST /auth/register-open に対応。
// 公開は NEXT_PUBLIC_PUBLIC_REGISTRATION_ENABLED フラグで gate（既定 false）。
import { useRouter } from 'next/navigation'
import { useState, FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle } from 'lucide-react'
import { registerOpen } from '@/lib/api/auth'
import { isPublicRegistrationEnabled } from '@/lib/flags'

function SignupForm() {
  const router = useRouter()

  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!consent) {
      setError('利用規約・プライバシーポリシーへの同意が必要です')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const result = await registerOpen({
        email,
        username,
        password,
        terms_consent: true,
      })
      localStorage.setItem('ultra_auth_token', result.access_token)
      localStorage.setItem('ultra_auth_expires', String(Date.now() + result.expires_in * 1000))
      router.replace('/user/dashboard')
    } catch (err: unknown) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message: string }).message)
          : '登録に失敗しました'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
          <CardDescription>新規アカウント登録</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="email">メールアドレス</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                disabled={submitting}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="username">表示名</Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                disabled={submitting}
                placeholder="山田太郎"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">パスワード</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                disabled={submitting}
              />
              <p className="text-xs text-muted-foreground">8文字以上で入力してください</p>
            </div>

            {/* 利用規約・プライバシーポリシー同意 */}
            <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 dark:border-blue-800 dark:bg-blue-950/20">
              <input
                id="consent"
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                required
                disabled={submitting}
                className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600"
              />
              <Label htmlFor="consent" className="text-xs leading-relaxed cursor-pointer">
                <a href="/terms" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-primary">
                  利用規約
                </a>
                および
                <a href="/privacy-policy" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-primary">
                  プライバシーポリシー
                </a>
                に同意します
              </Label>
            </div>

            <Button type="submit" className="w-full" disabled={submitting || !consent}>
              {submitting ? '登録中...' : 'アカウントを作成'}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            すでにアカウントをお持ちの方は
            <a href="/login" className="underline underline-offset-4 hover:text-primary ml-1">
              ログイン
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  )
}

function ComingSoon() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
          <CardDescription>新規アカウント登録</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              一般登録は現在準備中です。招待をお持ちの方は招待リンクからご登録ください。
            </AlertDescription>
          </Alert>
          <Button variant="outline" className="w-full" onClick={() => { window.location.href = '/login' }}>
            ログインへ
          </Button>
        </CardContent>
      </Card>
    </main>
  )
}

export default function SignupPage() {
  const enabled = isPublicRegistrationEnabled()
  return (
    <>
      <title>新規登録 - Ultra AutoTrade</title>
      {enabled ? <SignupForm /> : <ComingSoon />}
    </>
  )
}
