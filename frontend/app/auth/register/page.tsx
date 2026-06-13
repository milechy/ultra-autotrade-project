'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { useRouter, useSearchParams } from 'next/navigation'
import { useState, useEffect, FormEvent, Suspense } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { registerWithReferral } from '@/lib/api/referral'
import { setAuthToken } from "@/lib/auth/token-key"

function getReferralCookie(): string {
  if (typeof document === 'undefined') return ''
  const match = document.cookie.split('; ').find((row) => row.startsWith('referral_code='))
  return match ? decodeURIComponent(match.split('=')[1]) : ''
}

function RegisterWithReferralForm() {
  const t = useTranslations('AuthRegister')
  const router = useRouter()
  const searchParams = useSearchParams()
  const refCode = searchParams.get('ref') ?? ''

  const [referralCode, setReferralCode] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [noCode, setNoCode] = useState(false)

  useEffect(() => {
    const code = refCode || getReferralCookie()
    if (code) {
      setReferralCode(code)
    } else {
      setNoCode(true)
    }
  }, [refCode])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!consent) {
      setError(t('consentRequired'))
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const result = await registerWithReferral({
        email,
        password,
        username,
        referral_code: referralCode,
        referred_consent: true,
      })
      setAuthToken(result.access_token)
      localStorage.setItem('ultra_auth_expires', String(Date.now() + result.expires_in * 1000))
      // Clear referral cookie after successful registration
      document.cookie = 'referral_code=; max-age=0; path=/'
      router.replace('/user/dashboard')
    } catch (err: unknown) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message: string }).message)
          : t('registrationFailed')
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  if (noCode) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
        <Card className="w-full max-w-sm">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
            <CardDescription>{t('noCodeCardDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {t('noCodeErrorMessage')}
              </AlertDescription>
            </Alert>
            <Button variant="outline" className="w-full" onClick={() => router.replace('/login')}>
              {t('noCodeLoginButton')}
            </Button>
          </CardContent>
        </Card>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
          <CardDescription>{t('cardDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* 招待コード（読み取り専用） */}
            <div className="space-y-1.5">
              <Label>{t('referralCodeLabel')}</Label>
              <div className="flex items-center gap-2 rounded-md border border-input bg-muted px-3 py-2 text-sm font-mono">
                <span className="flex-1 truncate text-foreground">{referralCode}</span>
                <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
              </div>
              <p className="text-xs text-green-600">{t('referralCodeApplied')}</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">{t('emailLabel')}</Label>
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
              <Label htmlFor="username">{t('usernameLabel')}</Label>
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
              <Label htmlFor="password">{t('passwordLabel')}</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                disabled={submitting}
              />
            </div>

            {/* 紹介プログラム同意チェックボックス */}
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
                {t('consentText')}
              </Label>
            </div>

            <Button type="submit" className="w-full" disabled={submitting || !consent}>
              {submitting ? t('submittingButton') : t('submitButton')}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            {t('hasAccountText')}
            <a href="/login" className="underline underline-offset-4 hover:text-primary ml-1">
              {t('loginLink')}
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  )
}

export default function AuthRegisterPage() {
  return (
    <>
      <title>招待登録 - Ultra AutoTrade</title>
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center">
            <p className="text-muted-foreground">読み込み中...</p>
          </div>
        }
      >
        <RegisterWithReferralForm />
      </Suspense>
    </>
  )
}
